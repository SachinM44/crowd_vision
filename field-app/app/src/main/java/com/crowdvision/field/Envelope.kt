package com.crowdvision.field

import org.json.JSONObject
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale
import java.util.TimeZone
import java.util.concurrent.atomic.AtomicInteger

/**
 * docs/MESSAGES.md (v9 §e) envelope, hand-built.
 *
 * The phone cannot `import crowdvision`, so this is the Kotlin mirror of
 * `crowdvision._lib.messages`. Anything published from here MUST satisfy
 * `validate_envelope()`: {type, v, ts, src, seq, payload}, seq an int, and
 * AI messages (incident.report) carrying inference_backend/latency_ms/model_id.
 */
object Envelope {

    const val SCHEMA_VERSION = 1

    // Topics (docs/MESSAGES.md).
    fun topicOfficerBeacon(officerId: String) = "cv/officer/$officerId/beacon"
    fun topicDispatch(officerId: String) = "cv/dispatch/$officerId"
    fun topicHeartbeat(device: String) = "cv/sys/heartbeat/$device"
    const val TOPIC_INCIDENT_NEW = "cv/incident/new"

    // Message types.
    const val T_OFFICER_BEACON = "officer.beacon"
    const val T_INCIDENT_REPORT = "incident.report"
    const val T_HEARTBEAT = "sys.heartbeat"

    // Honest backend badges (Hard Rule 2 — badges never lie).
    const val BACKEND_LITERT_GPU = "litert-gpu"   // FunctionGemma really ran on GPU
    const val BACKEND_LITERT_NPU = "litert-npu"   // E2B probe really ran on the NPU
    const val BACKEND_CPU = "cpu"                 // keyword rules / dropdown form

    private val seq = AtomicInteger(0)

    /** ISO-8601 in IST with milliseconds — e.g. 2026-07-12T07:41:03.214+05:30 */
    fun nowTs(): String {
        val fmt = SimpleDateFormat("yyyy-MM-dd'T'HH:mm:ss.SSSXXX", Locale.US)
        fmt.timeZone = TimeZone.getTimeZone("Asia/Kolkata")
        return fmt.format(Date())
    }

    fun build(type: String, src: String, payload: JSONObject): JSONObject =
        JSONObject()
            .put("type", type)
            .put("v", SCHEMA_VERSION)
            .put("ts", nowTs())
            .put("src", src)
            .put("seq", seq.incrementAndGet())
            .put("payload", payload)
}
