package com.crowdvision.field

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.Context
import android.content.Intent
import android.location.Location
import android.location.LocationListener
import android.location.LocationManager
import android.os.BatteryManager
import android.os.Handler
import android.os.HandlerThread
import android.os.IBinder
import android.util.Log
import org.json.JSONObject
import java.util.UUID

/**
 * The officer node (BETA_HANDOFF §4F-§4I). Foreground service so beacons and
 * dispatch acks survive screen-off.
 *
 *  PUBLISH  cv/officer/{id}/beacon   every 3 s (QoS 0)
 *  SUBSCRIBE cv/dispatch/{id}        -> status=enroute + IMMEDIATE beacon whose
 *                                       ack_dispatch_id IS the ack (QoS 1)
 *  PUBLISH  cv/incident/new          structured incident (QoS 1)
 *  LWT/heartbeat cv/sys/heartbeat/{id} retained
 *
 * GPS is AOSP LocationManager (NOT Play Services — the phone must work with no
 * Google account and no data). If there is no fix yet we DO NOT beacon: a
 * fabricated coordinate would send an officer to the wrong place.
 */
class FieldService : Service() {

    companion object {
        const val ACTION_INCIDENT = "com.crowdvision.field.INCIDENT"
        const val EXTRA_PAYLOAD = "payload"
        private const val CHANNEL = "crowdvision-field"
        private const val NOTIF_ID = 42
        private const val BEACON_MS = 3000L
        private const val TAG = "cv-service"

        @Volatile
        var instance: FieldService? = null
    }

    private lateinit var worker: HandlerThread
    private lateinit var handler: Handler
    private var mqtt: Mqtt? = null
    private var locationManager: LocationManager? = null
    private var running = false

    private val locationListener = object : LocationListener {
        override fun onLocationChanged(loc: Location) {
            AppState.lat = loc.latitude
            AppState.lon = loc.longitude
            AppState.accuracyM = if (loc.hasAccuracy()) loc.accuracy else 0f
            AppState.notifyChanged()
        }

        @Deprecated("AOSP callback kept for older providers")
        override fun onStatusChanged(provider: String?, status: Int, extras: android.os.Bundle?) {}
        override fun onProviderEnabled(provider: String) {}
        override fun onProviderDisabled(provider: String) {}
    }

    private val beaconTick = object : Runnable {
        override fun run() {
            if (!running) return
            try {
                mqtt?.reconnectIfNeeded()
                publishBeacon()
            } catch (t: Throwable) {
                Log.w(TAG, "beacon tick: ${t.message}")
            }
            handler.postDelayed(this, BEACON_MS)
        }
    }

    override fun onCreate() {
        super.onCreate()
        instance = this
        AppState.load(this)
        createChannel()
        startForeground(NOTIF_ID, buildNotification())
        worker = HandlerThread("cv-field").apply { start() }
        handler = Handler(worker.looper)
        running = true

        handler.post {
            try {
                mqtt = Mqtt(AppState.officerId, AppState.brokerHost, AppState.brokerPort) { env ->
                    onDispatch(env)
                }.also { it.connect() }
            } catch (t: Throwable) {
                Log.e(TAG, "mqtt connect failed: ${t.message}")
                AppState.setEvent("broker unreachable: ${t.message}")
            }
        }
        startLocation()
        handler.postDelayed(beaconTick, 1500L)
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int = START_STICKY

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onDestroy() {
        running = false
        handler.removeCallbacksAndMessages(null)
        try {
            locationManager?.removeUpdates(locationListener)
        } catch (t: Throwable) {
            Log.w(TAG, "removeUpdates: ${t.message}")
        }
        handler.post { mqtt?.disconnect() }
        worker.quitSafely()
        instance = null
        super.onDestroy()
    }

    // -- GPS (AOSP) ----------------------------------------------------------
    private fun startLocation() {
        val lm = getSystemService(Context.LOCATION_SERVICE) as LocationManager
        locationManager = lm
        try {
            for (provider in listOf(LocationManager.GPS_PROVIDER, LocationManager.NETWORK_PROVIDER)) {
                if (lm.isProviderEnabled(provider)) {
                    lm.requestLocationUpdates(provider, 2000L, 1f, locationListener)
                    lm.getLastKnownLocation(provider)?.let { locationListener.onLocationChanged(it) }
                }
            }
        } catch (se: SecurityException) {
            Log.e(TAG, "location permission missing: ${se.message}")
            AppState.setEvent("location permission missing")
        }
    }

    private fun batteryPct(): Int {
        val bm = getSystemService(Context.BATTERY_SERVICE) as BatteryManager
        return bm.getIntProperty(BatteryManager.BATTERY_PROPERTY_CAPACITY)
    }

    // -- beacon (the ack channel too) ----------------------------------------
    private fun publishBeacon() {
        val lat = AppState.lat
        val lon = AppState.lon
        if (lat == null || lon == null) return   // never fabricate a position
        val payload = OfficerLogic.beaconPayload(
            officerId = AppState.officerId,
            lat = lat, lon = lon,
            accuracyM = AppState.accuracyM.toDouble(),
            status = AppState.status,
            batteryPct = batteryPct(),
            ackDispatchId = AppState.ackDispatchId,
        )
        mqtt?.publish(
            Envelope.topicOfficerBeacon(AppState.officerId),
            Envelope.T_OFFICER_BEACON, payload, qos = 0
        )
    }

    private fun onDispatch(env: JSONObject) {
        val d = OfficerLogic.parseDispatch(env, AppState.officerId) ?: return
        AppState.status = "enroute"
        AppState.ackDispatchId = d.dispatchId
        AppState.lastDispatchReason = d.reason
        AppState.setEvent("DISPATCH ${d.dispatchId}: ${d.reason}")
        publishBeacon()   // the beacon carrying ack_dispatch_id IS the ack (§4G)
    }

    fun clearDispatch() {
        AppState.status = "available"
        AppState.ackDispatchId = null
        AppState.setEvent("available")
        handler.post { publishBeacon() }
    }

    // -- incident ------------------------------------------------------------
    /**
     * Publishes a validated incident. `result` carries the honest badges of
     * whatever actually produced the structure. A schema-invalid structure is
     * NOT published (§4H) — the caller shows the dropdown form instead.
     */
    fun publishIncident(text: String, result: StructureResult, photoRef: String?): Boolean {
        if (!result.schemaValid || result.structured == null) {
            AppState.setEvent("schema INVALID — not published; use the form")
            return false
        }
        val payload = OfficerLogic.incidentPayload(
            incidentId = "inc-" + UUID.randomUUID().toString().take(8),
            officerId = AppState.officerId,
            lat = AppState.lat, lon = AppState.lon,
            text = text, result = result, photoRef = photoRef,
        )
        handler.post {
            mqtt?.publish(Envelope.TOPIC_INCIDENT_NEW, Envelope.T_INCIDENT_REPORT, payload, qos = 1)
        }
        AppState.setEvent("incident sent (${result.modelId} / ${result.backend})")
        return true
    }

    // -- notification --------------------------------------------------------
    private fun createChannel() {
        val nm = getSystemService(NotificationManager::class.java)
        nm.createNotificationChannel(
            NotificationChannel(CHANNEL, "CrowdVision Field", NotificationManager.IMPORTANCE_LOW)
        )
    }

    private fun buildNotification(): Notification {
        val pi = PendingIntent.getActivity(
            this, 0, Intent(this, MainActivity::class.java),
            PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT
        )
        return Notification.Builder(this, CHANNEL)
            .setContentTitle("CrowdVision — ${AppState.officerId}")
            .setContentText("On duty: beacon + dispatch active")
            .setSmallIcon(android.R.drawable.ic_menu_mylocation)
            .setContentIntent(pi)
            .setOngoing(true)
            .build()
    }
}
