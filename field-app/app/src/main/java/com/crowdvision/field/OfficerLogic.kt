package com.crowdvision.field

import org.json.JSONObject

/**
 * The officer's contract behaviour, with no Android in it.
 *
 * FieldService owns the threads, GPS and MQTT socket; the rules about WHAT to
 * say live here so they can be executed off-device against a real broker
 * (see MqttLiveTest) instead of being trusted because the code "looks right".
 */
object OfficerLogic {

    data class Dispatch(val dispatchId: String, val reason: String)

    /** cv/officer/{id}/beacon (§4F). `ackDispatchId` non-null == this IS the ack. */
    fun beaconPayload(
        officerId: String,
        lat: Double,
        lon: Double,
        accuracyM: Double,
        status: String,
        batteryPct: Int,
        ackDispatchId: String?,
    ): JSONObject = JSONObject()
        .put("officer_id", officerId)
        .put("lat", lat)
        .put("lon", lon)
        .put("accuracy_m", accuracyM)
        .put("status", status)
        .put("battery_pct", batteryPct)
        .put("ack_dispatch_id", ackDispatchId ?: JSONObject.NULL)

    /**
     * cv/dispatch/{id} (§4G). Returns null when the order is not ours — the
     * broker topic is per-officer, but never trust the topic alone.
     */
    fun parseDispatch(env: JSONObject, officerId: String): Dispatch? {
        val p = env.optJSONObject("payload") ?: return null
        if (p.optString("officer_id") != officerId) return null
        val id = p.optString("dispatch_id")
        if (id.isEmpty()) return null
        return Dispatch(id, p.optString("reason"))
    }

    /**
     * cv/incident/new (§4H). Carries the honest badges of whatever actually
     * produced the structure. Callers MUST NOT call this when
     * `result.schemaValid` is false — an unvalidated structure is a no-op.
     */
    fun incidentPayload(
        incidentId: String,
        officerId: String,
        lat: Double?,
        lon: Double?,
        text: String,
        result: StructureResult,
        photoRef: String?,
    ): JSONObject {
        require(result.schemaValid && result.structured != null) {
            "refusing to build an incident from a schema-invalid structure"
        }
        return JSONObject()
            .put("incident_id", incidentId)
            .put("officer_id", officerId)
            .put("lat", lat ?: JSONObject.NULL)
            .put("lon", lon ?: JSONObject.NULL)
            .put("text", text)
            .put("structured", result.structured.toJson())
            .put("schema_valid", true)
            .put("photo_ref", photoRef ?: JSONObject.NULL)
            .put("model_id", result.modelId)
            .put("inference_backend", result.backend)
            .put("latency_ms", result.latencyMs)
            .put("ttft_ms", result.ttftMs)
    }
}
