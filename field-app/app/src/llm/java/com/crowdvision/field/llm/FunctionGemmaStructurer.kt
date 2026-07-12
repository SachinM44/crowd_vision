package com.crowdvision.field.llm

import android.content.Context
import android.util.Log
import com.crowdvision.field.Envelope
import com.crowdvision.field.IncidentStructurer
import com.crowdvision.field.Models
import com.crowdvision.field.Schema
import com.crowdvision.field.StructureResult
import com.crowdvision.field.StructurerFactory
import org.json.JSONObject
import java.io.File

/**
 * FunctionGemma 270M via LiteRT-LM (BETA_HANDOFF §4H).
 *
 * Compiled ONLY with `-PwithLlm=true`; loaded by reflection from
 * StructurerFactory, so the shipped app builds even without the dependency.
 *
 * BADGE HONESTY (Hard Rule 2 — this is the disqualification-grade one):
 * the provided artifact `Mobile_actions_q8_ekv1024.litertlm` is a CPU/GPU build.
 * There is no sm8750 NPU build of FunctionGemma. So we request Backend.GPU()
 * and badge `litert-gpu` — NEVER `litert-npu`. The only thing allowed to claim
 * `litert-npu` is the E2B probe below, and only when it actually ran.
 *
 * ENGINE SEAM: LiteRT-LM's Kotlin surface moves between releases. Everything
 * version-specific lives in LlmEngine (reflection over the shipped classes), so
 * a renamed method is a one-place fix, not a rewrite. If the engine cannot be
 * constructed we throw — StructurerFactory then falls back to keyword rules and
 * the badge tells the truth about it.
 */
class FunctionGemmaStructurer(private val ctx: Context) : IncidentStructurer {

    private val tag = "cv-functiongemma"
    private val engine: LlmEngine

    init {
        val model = StructurerFactory.modelCandidates(ctx).firstOrNull { it.exists() }
            ?: throw IllegalStateException(
                "${Models.FUNCTIONGEMMA} not found — adb push it to " +
                    "${ctx.getExternalFilesDir("models")?.absolutePath} or use Import model")
        Log.i(tag, "loading ${model.name} (${model.length() / (1024 * 1024)} MB) on GPU")
        engine = LlmEngine.create(ctx, model, useNpu = false)   // GPU — see note above
    }

    override fun structure(text: String): StructureResult {
        val prompt = buildPrompt(text)
        val t0 = System.currentTimeMillis()
        var ttft = 0L
        var tokens = 0

        val raw = engine.generate(prompt) { _ ->
            if (ttft == 0L) ttft = System.currentTimeMillis() - t0
            tokens++
        }
        val latency = System.currentTimeMillis() - t0
        if (ttft == 0L) ttft = latency   // non-streaming engine: TTFT == latency

        val structured = Schema.parse(raw)
        val valid = Schema.validate(structured)
        if (!valid) Log.w(tag, "schema-invalid output (no-op): $raw")

        return StructureResult(
            structured = structured,
            schemaValid = valid,
            modelId = Models.FUNCTIONGEMMA_ID,
            backend = Envelope.BACKEND_LITERT_GPU,   // what ACTUALLY ran
            latencyMs = latency,
            ttftMs = ttft,
            raw = raw,
            tokens = tokens,
        )
    }

    override fun close() = engine.close()

    /**
     * FunctionGemma is a function-calling specialist: declare exactly one tool
     * and let it fill the arguments. Keep the enums identical to Schema's — a
     * value outside them fails validation and is dropped rather than published.
     */
    private fun buildPrompt(text: String): String = buildString {
        append("<start_of_turn>developer\n")
        append("You report field incidents at a crowded public event by calling one function.\n")
        append("<tool_declarations>")
        append("""[{"name":"report_incident","description":"Report a field incident",""")
        append(""""parameters":{"type":"object","properties":{""")
        append(""""type":{"type":"string","enum":["medical","crush-risk","fire","security","lost-person","other"]},""")
        append(""""location_hint":{"type":"string","description":"where, e.g. Gate 3"},""")
        append(""""severity":{"type":"string","enum":["low","medium","high"]},""")
        append(""""needs":{"type":"array","items":{"type":"string"},"description":"e.g. medic, stretcher, crowd-control"}},""")
        append(""""required":["type","location_hint","severity","needs"]}}]""")
        append("</tool_declarations><end_of_turn>\n")
        append("<start_of_turn>user\n")
        append(text)
        append("<end_of_turn>\n")
        append("<start_of_turn>model\n")
    }

    companion object {
        /**
         * E2B NPU probe (§4J) — benchmark ONLY, called from Bench via reflection.
         * Requires the Qualcomm .so set in jniLibs (never redistributed).
         * Success badges `litert-npu`; anything else is recorded as a failure row.
         */
        @JvmStatic
        fun probeE2b(ctx: Context, model: File): JSONObject {
            val t0 = System.currentTimeMillis()
            val engine = LlmEngine.create(ctx, model, useNpu = true)
            var ttft = 0L
            var tokens = 0
            val out = engine.generate("Summarise crowd safety in one sentence.") { _ ->
                if (ttft == 0L) ttft = System.currentTimeMillis() - t0
                tokens++
            }
            val latency = System.currentTimeMillis() - t0
            engine.close()
            val tokPerS = if (latency > 0) tokens * 1000.0 / latency else 0.0
            val md = "| metric | value |\n|---|---|\n" +
                "| result | **OK — ran on the NPU** |\n" +
                "| model_id | `${Models.E2B_ID}` |\n" +
                "| inference_backend | `${Envelope.BACKEND_LITERT_NPU}` (Hexagon v81) |\n" +
                "| TTFT | $ttft ms |\n" +
                "| decode | ${"%.1f".format(tokPerS)} tok/s |\n" +
                "| tokens | $tokens |\n\n" +
                "> Benchmark only. FunctionGemma 270M (`litert-gpu`) remains the shipped " +
                "structurer — a 270M specialist beats a 2B generalist at emitting one " +
                "validated call."
            return JSONObject()
                .put("markdown", md)
                .put("captured_at", Envelope.nowTs())
                .put("model_id", Models.E2B_ID)
                .put("inference_backend", Envelope.BACKEND_LITERT_NPU)
                .put("ttft_ms", ttft)
                .put("tokens", tokens)
                .put("tok_per_s", tokPerS)
                .put("sample", out.take(200))
        }
    }
}
