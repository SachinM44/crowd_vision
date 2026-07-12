package com.crowdvision.field

import android.util.Log
import org.eclipse.paho.client.mqttv3.IMqttDeliveryToken
import org.eclipse.paho.client.mqttv3.MqttAsyncClient
import org.eclipse.paho.client.mqttv3.MqttCallbackExtended
import org.eclipse.paho.client.mqttv3.MqttConnectOptions
import org.eclipse.paho.client.mqttv3.MqttMessage
import org.eclipse.paho.client.mqttv3.persist.MemoryPersistence
import org.json.JSONObject

/**
 * Paho JAVA client (the Android *Service* artifact is unmaintained and breaks on
 * API 31+). We own the lifecycle from FieldService.
 *
 * Contract bits that matter (BETA_HANDOFF §4F-§4I):
 *  - LWT on cv/sys/heartbeat/{device}, QoS 1 RETAINED, set BEFORE connect.
 *  - keepalive 15 s (matches the broker).
 *  - cleanSession=true kills subscriptions on reconnect, so we resubscribe and
 *    republish the retained "online" heartbeat in connectComplete(), which fires
 *    on the first connect AND on every automatic reconnect.
 */
class Mqtt(
    private val device: String,
    private val host: String,
    private val port: Int,
    private val onDispatch: (JSONObject) -> Unit,
) {
    private val tag = "cv-mqtt"
    private var client: MqttAsyncClient? = null
    private val dispatchTopic = Envelope.topicDispatch(device)

    val isConnected: Boolean get() = client?.isConnected == true

    fun connect() {
        val c = MqttAsyncClient("tcp://$host:$port", "cv-$device", MemoryPersistence())
        val lwt = Envelope.build(
            Envelope.T_HEARTBEAT, device,
            JSONObject().put("device", device).put("state", "offline").put("reason", "lwt")
        )
        val opts = MqttConnectOptions().apply {
            isCleanSession = true
            isAutomaticReconnect = true
            keepAliveInterval = 15
            connectionTimeout = 10
            setWill(Envelope.topicHeartbeat(device), lwt.toString().toByteArray(), 1, true)
        }
        c.setCallback(object : MqttCallbackExtended {
            override fun connectComplete(reconnect: Boolean, serverURI: String) {
                Log.i(tag, "connected (reconnect=$reconnect) to $serverURI")
                c.subscribe(dispatchTopic, 1)          // cleanSession drops subs
                heartbeat("online")                    // retained, so the dashboard sees us
                AppState.setConnected(true)
            }

            override fun connectionLost(cause: Throwable?) {
                Log.w(tag, "connection lost: ${cause?.message}")
                AppState.setConnected(false)
            }

            override fun messageArrived(topic: String, message: MqttMessage) {
                if (topic != dispatchTopic) return
                try {
                    onDispatch(JSONObject(String(message.payload)))
                } catch (t: Throwable) {
                    Log.w(tag, "bad dispatch payload: ${t.message}")
                }
            }

            override fun deliveryComplete(token: IMqttDeliveryToken?) {}
        })
        client = c
        c.connect(opts)
    }

    /** Paho's auto-reconnect can stall after a Wi-Fi flap — nudge it. */
    fun reconnectIfNeeded() {
        val c = client ?: return
        if (c.isConnected) return
        try {
            c.reconnect()
        } catch (t: Throwable) {
            Log.w(tag, "reconnect failed: ${t.message}")
        }
    }

    fun publish(topic: String, type: String, payload: JSONObject, qos: Int, retain: Boolean = false) {
        val c = client ?: return
        if (!c.isConnected) return
        try {
            val env = Envelope.build(type, device, payload)
            c.publish(topic, env.toString().toByteArray(), qos, retain)
        } catch (t: Throwable) {
            Log.w(tag, "publish $type failed: ${t.message}")
        }
    }

    fun heartbeat(state: String) {
        publish(
            Envelope.topicHeartbeat(device), Envelope.T_HEARTBEAT,
            JSONObject().put("device", device).put("state", state),
            qos = 1, retain = true
        )
    }

    /** Clean shutdown publishes "offline" itself so the LWT never fires. */
    fun disconnect() {
        val c = client ?: return
        try {
            if (c.isConnected) {
                heartbeat("offline")
                Thread.sleep(200)
                c.disconnect()
            }
            c.close()
        } catch (t: Throwable) {
            Log.w(tag, "disconnect: ${t.message}")
        }
        client = null
        AppState.setConnected(false)
    }
}
