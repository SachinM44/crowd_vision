package com.crowdvision.field

import android.content.Context
import android.util.Log
import org.json.JSONArray
import org.json.JSONObject
import java.io.File

/**
 * BENCH:functiongemma + BENCH:e2b_probe (BETA_HANDOFF §5, docs/BENCHMARKS.md).
 *
 * Writes bench/embed.py-shaped JSON ({markdown, captured_at}) to the app's
 * external files dir. Pull it with:
 *   adb pull /sdcard/Android/data/com.crowdvision.field/files/bench/functiongemma.json \
 *            bench/out/functiongemma.json
 *   python bench/embed.py
 *
 * The numbers are whatever actually ran — if the keyword fallback produced them,
 * the markdown says so, loudly. Never present rules-on-CPU as an NPU/GPU number.
 */
object Bench {

    private const val TAG = "BENCH"

    /** 20 scripted incident texts covering every incident type. */
    private val SCRIPTED = listOf(
        "man collapsed near gate 2 barrier, crowd gathering",
        "woman fainted by the east stage, needs a medic",
        "elderly man unconscious at exit 4, not breathing well",
        "child bleeding from a fall near zone C food stalls",
        "someone had a seizure close to gate 1",
        "crowd crushing against the barrier at gate 3, people shouting",
        "dangerous surge building near the main stage front",
        "people getting squeezed at the zone B bottleneck",
        "too many people pushing towards exit 2",
        "crowd packed solid near gate 3, cannot move",
        "smoke coming from behind the food stall in zone D",
        "small fire near the generator at the north exit",
        "fight broke out near gate 1, two men",
        "man with a knife reported close to zone A entrance",
        "theft reported near the merchandise tent",
        "lost child near the ferris wheel, about six years old",
        "girl separated from her parents at zone B",
        "spilled water making the floor slippery at gate 2",
        "barrier broken near stage left, people leaning on it",
        "drunk man causing trouble outside exit 3",
    )

    fun runFunctionGemmaBench(ctx: Context, structurer: IncidentStructurer): String {
        val ttfts = mutableListOf<Long>()
        val lats = mutableListOf<Long>()
        val toksPerS = mutableListOf<Double>()
        var valid = 0
        var modelId = "?"
        var backend = "?"

        for (text in SCRIPTED) {
            val r = try {
                structurer.structure(text)
            } catch (t: Throwable) {
                Log.w(TAG, "bench item failed: ${t.message}")
                continue
            }
            modelId = r.modelId
            backend = r.backend
            ttfts.add(r.ttftMs)
            lats.add(r.latencyMs)
            if (r.tokens > 0 && r.latencyMs > 0) {
                toksPerS.add(r.tokens * 1000.0 / r.latencyMs)
            }
            if (r.schemaValid) valid++
        }

        if (ttfts.isEmpty()) return "bench produced no samples"

        val n = ttfts.size
        val honest = backend == Envelope.BACKEND_LITERT_GPU || backend == Envelope.BACKEND_LITERT_NPU
        val note = if (honest) "" else
            "\n\n> **Not a model benchmark.** The FunctionGemma engine was unavailable, so " +
            "these are the deterministic keyword-rule fallback's numbers (backend `$backend`). " +
            "They are NOT LiteRT/GPU inference numbers."

        val md = buildString {
            append("| metric | value |\n|---|---|\n")
            append("| model_id | `$modelId` |\n")
            append("| inference_backend | `$backend` |\n")
            append("| scripted prompts | $n |\n")
            append("| TTFT p50 | ${pct(ttfts, 0.50)} ms |\n")
            append("| TTFT p95 | ${pct(ttfts, 0.95)} ms |\n")
            append("| latency p50 | ${pct(lats, 0.50)} ms |\n")
            append("| latency p95 | ${pct(lats, 0.95)} ms |\n")
            if (toksPerS.isNotEmpty()) {
                append("| decode mean | ${"%.1f".format(toksPerS.average())} tok/s |\n")
            }
            append("| schema-valid rate | $valid/$n (${valid * 100 / n}%) |\n")
            append(note)
        }

        val doc = JSONObject()
            .put("markdown", md)
            .put("captured_at", Envelope.nowTs())
            .put("model_id", modelId)
            .put("inference_backend", backend)
            .put("schema_valid", valid)
            .put("n", n)
            .put("ttft_ms", JSONArray(ttfts))
            .put("latency_ms", JSONArray(lats))

        return write(ctx, "functiongemma.json", doc, md)
    }

    /**
     * E2B NPU probe (§4J): benchmark-only, 30-minute timebox, never the shipped
     * structurer. Success badges `litert-npu`; failure records the exact error —
     * both are legitimate benchmark rows.
     */
    fun runE2bProbe(ctx: Context): String {
        val model = File(ctx.getExternalFilesDir("models"), Models.E2B)
        if (!BuildConfig.WITH_LLM) {
            return "E2B probe needs the -PwithLlm build (LiteRT-LM not compiled in)."
        }
        if (!model.exists()) {
            return "E2B probe: model not found at ${model.absolutePath}\n" +
                "adb push ${Models.E2B} to that folder first."
        }
        return try {
            val cls = Class.forName("com.crowdvision.field.llm.FunctionGemmaStructurer")
            val m = cls.getMethod("probeE2b", Context::class.java, File::class.java)
            @Suppress("UNCHECKED_CAST")
            val result = m.invoke(null, ctx, model) as JSONObject
            val md = result.optString("markdown", "(no markdown)")
            write(ctx, "e2b_probe.json", result, md)
        } catch (t: Throwable) {
            val err = "${t.javaClass.simpleName}: ${t.cause?.message ?: t.message}"
            Log.w(TAG, "E2B probe failed: $err")
            val md = "| metric | value |\n|---|---|\n" +
                "| result | **FAILED** |\n" +
                "| backend attempted | `${Envelope.BACKEND_LITERT_NPU}` (Hexagon v81) |\n" +
                "| error | `$err` |\n\n" +
                "> Recorded honestly. FunctionGemma (`litert-gpu`) remains the shipped " +
                "structurer — the probe was always benchmark-only."
            val doc = JSONObject().put("markdown", md)
                .put("captured_at", Envelope.nowTs()).put("error", err)
            write(ctx, "e2b_probe.json", doc, md)
        }
    }

    private fun write(ctx: Context, name: String, doc: JSONObject, md: String): String {
        val dir = File(ctx.getExternalFilesDir("bench"), "").apply { mkdirs() }
        val f = File(dir, name)
        f.writeText(doc.toString(2))
        Log.i(TAG, "$name\n$md")
        return f.absolutePath
    }

    private fun pct(xs: List<Long>, q: Double): Long {
        if (xs.isEmpty()) return 0
        val s = xs.sorted()
        return s[minOf((s.size * q).toInt(), s.size - 1)]
    }
}
