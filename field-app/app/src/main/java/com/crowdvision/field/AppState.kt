package com.crowdvision.field

import android.content.Context

/**
 * Shared state between MainActivity (UI) and FieldService (MQTT + GPS).
 * Plain singleton + listener — no coroutines, no LiveData: this app has to be
 * boringly reliable at 03:00.
 */
object AppState {

    private const val PREFS = "crowdvision"

    @Volatile var brokerHost: String = "192.168.1.10"
    @Volatile var brokerPort: Int = 1883
    @Volatile var officerId: String = "officer-1"

    @Volatile var connected: Boolean = false; private set
    @Volatile var status: String = "available"          // available | enroute
    @Volatile var lat: Double? = null                   // null until a real GPS fix
    @Volatile var lon: Double? = null
    @Volatile var accuracyM: Float = 0f
    @Volatile var ackDispatchId: String? = null
    @Volatile var lastDispatchReason: String? = null
    @Volatile var lastEvent: String = "idle"

    private val listeners = mutableListOf<() -> Unit>()

    fun load(ctx: Context) {
        val p = ctx.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
        brokerHost = p.getString("brokerHost", brokerHost)!!
        brokerPort = p.getInt("brokerPort", brokerPort)
        officerId = p.getString("officerId", officerId)!!
    }

    fun save(ctx: Context) {
        ctx.getSharedPreferences(PREFS, Context.MODE_PRIVATE).edit()
            .putString("brokerHost", brokerHost)
            .putInt("brokerPort", brokerPort)
            .putString("officerId", officerId)
            .apply()
    }

    fun addListener(l: () -> Unit) = synchronized(listeners) { listeners.add(l) }
    fun removeListener(l: () -> Unit) = synchronized(listeners) { listeners.remove(l) }

    fun notifyChanged() {
        val snapshot = synchronized(listeners) { listeners.toList() }
        snapshot.forEach { it() }
    }

    fun setConnected(v: Boolean) {
        connected = v
        notifyChanged()
    }

    fun setEvent(msg: String) {
        lastEvent = msg
        notifyChanged()
    }
}
