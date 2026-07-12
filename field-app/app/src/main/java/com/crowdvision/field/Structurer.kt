package com.crowdvision.field

import android.content.Context
import android.util.Log
import org.json.JSONArray
import org.json.JSONObject

/**
 * The incident AI beat (BETA_HANDOFF §4H).
 *
 * free text -> report_incident(type, location_hint, severity, needs[]) -> validate
 *
 * INVALID OUTPUT IS A NO-OP. A model that hallucinates a field does not get to
 * dispatch an officer — the UI falls back to the dropdown form instead. That
 * rule is enforced here, once, for every structurer.
 *
 * Badge honesty (Hard Rule 2): each impl reports what ACTUALLY ran.
 *   FunctionGemmaStructurer (src/llm, -PwithLlm) -> "functiongemma-270m" / "litert-gpu"
 *   KeywordStructurer  (always compiled)         -> "keyword-rules"     / "cpu"
 *   dropdown form (MainActivity, no structurer)  -> "dropdown-form"     / "cpu"
 */

val INCIDENT_TYPES = listOf("medical", "crush-risk", "fire", "security", "lost-person", "other")
val SEVERITIES = listOf("low", "medium", "high")

data class StructuredIncident(
    val type: String,
    val locationHint: String,
    val severity: String,
    val needs: List<String>,
) {
    fun toJson(): JSONObject = JSONObject()
        .put("type", type)
        .put("location_hint", locationHint)
        .put("severity", severity)
        .put("needs", JSONArray(needs))
}

data class StructureResult(
    val structured: StructuredIncident?,
    val schemaValid: Boolean,
    val modelId: String,
    val backend: String,
    val latencyMs: Long,
    val ttftMs: Long,
    val raw: String = "",
    val tokens: Int = 0,
)

interface IncidentStructurer {
    fun structure(text: String): StructureResult
    fun close() {}
}

/** The one schema gate. Anything that fails it never reaches the broker. */
object Schema {
    fun validate(s: StructuredIncident?): Boolean {
        if (s == null) return false
        if (s.type !in INCIDENT_TYPES) return false
        if (s.severity !in SEVERITIES) return false
        if (s.locationHint.isBlank()) return false
        if (s.needs.isEmpty() || s.needs.any { it.isBlank() }) return false
        return true
    }

    /**
     * Defensive parse of whatever the model emitted. FunctionGemma may answer
     * with a tool_call JSON block, a fenced ```tool_code print(report_incident(
     * type="medical", ...))``` line, or a bare JSON object. Try all; give up
     * honestly rather than guess a field.
     */
    fun parse(raw: String): StructuredIncident? =
        parseJsonObject(raw) ?: parseKwargs(raw)

    private fun parseJsonObject(raw: String): StructuredIncident? {
        val start = raw.indexOf('{')
        val end = raw.lastIndexOf('}')
        if (start < 0 || end <= start) return null
        return try {
            var o = JSONObject(raw.substring(start, end + 1))
            // Unwrap {"name": "report_incident", "parameters"/"arguments": {...}}
            for (key in listOf("parameters", "arguments", "args")) {
                if (o.has(key) && o.optJSONObject(key) != null) {
                    o = o.getJSONObject(key)
                    break
                }
            }
            val needs = mutableListOf<String>()
            o.optJSONArray("needs")?.let { arr ->
                for (i in 0 until arr.length()) needs.add(arr.getString(i).trim())
            }
            if (needs.isEmpty()) {
                o.optString("needs").takeIf { it.isNotBlank() }
                    ?.split(",")?.forEach { needs.add(it.trim()) }
            }
            StructuredIncident(
                type = o.optString("type").trim().lowercase(),
                locationHint = o.optString("location_hint").trim(),
                severity = o.optString("severity").trim().lowercase(),
                needs = needs.filter { it.isNotBlank() },
            )
        } catch (t: Throwable) {
            null
        }
    }

    /** report_incident(type="medical", location_hint="gate 2", severity="high", needs=["medic"]) */
    private fun parseKwargs(raw: String): StructuredIncident? {
        if (!raw.contains("report_incident")) return null
        val kv = Regex("""(\w+)\s*=\s*(\[[^\]]*\]|"[^"]*"|'[^']*')""")
            .findAll(raw)
            .associate { m ->
                m.groupValues[1] to m.groupValues[2].trim('"', '\'')
            }
        if (kv.isEmpty()) return null
        val needs = kv["needs"].orEmpty()
            .trim('[', ']')
            .split(",")
            .map { it.trim().trim('"', '\'') }
            .filter { it.isNotBlank() }
        return StructuredIncident(
            type = kv["type"].orEmpty().trim().lowercase(),
            locationHint = kv["location_hint"].orEmpty().trim(),
            severity = kv["severity"].orEmpty().trim().lowercase(),
            needs = needs,
        )
    }
}

/**
 * Zero-model fallback so the app ALWAYS ships. Honest badges: this is rules on
 * the CPU, and it says so. It never claims to be FunctionGemma.
 */
class KeywordStructurer : IncidentStructurer {

    private val typeRules = listOf(
        "medical" to listOf("collapse", "collapsed", "faint", "unconscious", "injur",
            "bleed", "medic", "ambulance", "chest", "breath", "seizure", "heat stroke"),
        "crush-risk" to listOf("crush", "surge", "stampede", "push", "packed", "squeeze",
            "bottleneck", "too many", "crowd building", "barrier"),
        "fire" to listOf("fire", "smoke", "burn", "flame", "spark"),
        "security" to listOf("fight", "weapon", "knife", "theft", "assault", "brawl",
            "threat", "aggress"),
        "lost-person" to listOf("lost", "missing", "child", "kid", "separated"),
    )

    private val needRules = listOf(
        "medic" to listOf("collapse", "injur", "bleed", "medic", "unconscious", "faint",
            "breath", "chest", "seizure"),
        "stretcher" to listOf("collapse", "unconscious", "cannot walk", "can't walk"),
        "crowd-control" to listOf("crush", "surge", "push", "packed", "stampede",
            "barrier", "crowd"),
        "fire-team" to listOf("fire", "smoke", "flame"),
        "security-team" to listOf("fight", "weapon", "knife", "assault", "threat", "brawl"),
        "announcement" to listOf("lost", "missing", "child", "separated"),
    )

    override fun structure(text: String): StructureResult {
        val t0 = System.currentTimeMillis()
        val lower = text.lowercase()

        val type = typeRules.firstOrNull { (_, keys) -> keys.any { lower.contains(it) } }
            ?.first ?: "other"

        val severity = when {
            listOf("unconscious", "not breathing", "crush", "stampede", "fire", "weapon",
                "collapse", "bleeding heavily").any { lower.contains(it) } -> "high"
            listOf("hurt", "injur", "fight", "lost", "push", "packed", "smoke")
                .any { lower.contains(it) } -> "medium"
            else -> "low"
        }

        val needs = needRules.filter { (_, keys) -> keys.any { lower.contains(it) } }
            .map { it.first }
            .ifEmpty { listOf("steward") }

        // Location hint: the phrase after a positional preposition, else the zone/gate token.
        val locMatch = Regex("""\b(?:near|at|by|beside|next to|outside|inside)\s+([\w\s\-]{2,40})""")
            .find(lower)?.groupValues?.get(1)?.trim()
        val gateMatch = Regex("""\b(gate\s*\w+|zone\s*\w+|stage\s*\w+|exit\s*\w+)""")
            .find(lower)?.groupValues?.get(1)?.trim()
        val locationHint = (gateMatch ?: locMatch ?: "officer position").take(40)

        val s = StructuredIncident(type, locationHint, severity, needs)
        val latency = System.currentTimeMillis() - t0
        return StructureResult(
            structured = s,
            schemaValid = Schema.validate(s),
            modelId = "keyword-rules",
            backend = Envelope.BACKEND_CPU,      // honest: no model ran
            latencyMs = latency,
            ttftMs = latency,
            raw = "keyword-rules",
        )
    }
}

/**
 * Loads the FunctionGemma structurer if it was compiled in (-PwithLlm=true) AND
 * the .litertlm model is present; otherwise falls back to keyword rules. The
 * reflection seam is what lets the main source set compile with no LiteRT-LM
 * dependency on the classpath.
 */
object StructurerFactory {

    fun best(ctx: Context): IncidentStructurer {
        if (!BuildConfig.WITH_LLM) return KeywordStructurer()
        return try {
            val cls = Class.forName("com.crowdvision.field.llm.FunctionGemmaStructurer")
            cls.getConstructor(Context::class.java).newInstance(ctx) as IncidentStructurer
        } catch (t: Throwable) {
            Log.w("cv-structurer", "FunctionGemma unavailable (${t.javaClass.simpleName}: " +
                "${t.message}) — falling back to keyword rules")
            KeywordStructurer()
        }
    }

    /** Where the .litertlm lives. adb push here, or use the in-app import button. */
    fun modelCandidates(ctx: Context): List<java.io.File> = listOf(
        java.io.File(ctx.getExternalFilesDir("models"), Models.FUNCTIONGEMMA),
        java.io.File(ctx.filesDir, "models/${Models.FUNCTIONGEMMA}"),
    )
}

object Models {
    const val FUNCTIONGEMMA = "Mobile_actions_q8_ekv1024.litertlm"
    const val E2B = "gemma-4-E2B-it_qualcomm_sm8750.litertlm"
    const val FUNCTIONGEMMA_ID = "functiongemma-270m"
    const val E2B_ID = "gemma-4-e2b-it"
}
