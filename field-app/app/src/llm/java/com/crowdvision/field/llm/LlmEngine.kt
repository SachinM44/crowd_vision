package com.crowdvision.field.llm

import android.content.Context
import android.util.Log
import java.io.File

/**
 * The ONE place that knows LiteRT-LM's concrete API.
 *
 * Why reflection instead of typed calls: LiteRT-LM's Kotlin surface (Engine /
 * EngineConfig / Backend, session vs. engine-level generate, streaming callback
 * shape) has moved between releases, and we build against whichever AAR/Maven
 * artifact resolves on the day. Compiling directly against a guessed signature
 * turns a 5-minute swap into a rebuild of the app. So: bind late, fail loudly,
 * and let StructurerFactory fall back to keyword rules with an honest badge if
 * the engine cannot be constructed at all.
 *
 * If you are holding the working LiteRT-LM sample: replace the body of create()
 * and generate() with the direct calls from it. That is a strict improvement —
 * keep the same class shape and nothing else changes.
 *
 *   val cfg = EngineConfig(modelPath = f.absolutePath, backend = Backend.GPU())
 *   val engine = Engine(cfg); engine.generate(prompt) { tok -> ... }
 */
class LlmEngine private constructor(
    private val impl: Any,
    private val generateFn: (Any, String, (String) -> Unit) -> String,
    private val closeFn: (Any) -> Unit,
) {
    fun generate(prompt: String, onToken: (String) -> Unit): String =
        generateFn(impl, prompt, onToken)

    fun close() = closeFn(impl)

    companion object {
        private const val TAG = "cv-llmengine"

        /**
         * @param useNpu false => Backend.GPU() (FunctionGemma: the artifact is a
         *   CPU/GPU build, so GPU is the honest ceiling).
         *   true => Backend.NPU(nativeLibDir) — E2B probe only.
         */
        fun create(ctx: Context, model: File, useNpu: Boolean): LlmEngine {
            val nativeLibDir = ctx.applicationInfo.nativeLibraryDir

            litertLm(model, useNpu, nativeLibDir)?.let { return it }
            mediaPipe(ctx, model)?.let { return it }

            throw IllegalStateException(
                "No LiteRT-LM engine on the classpath. Drop the LiteRT-LM AAR into " +
                    "field-app/app/libs/ and rebuild with -PwithLlm=true.")
        }

        /** Primary: LiteRT-LM (google-ai-edge). Engine + EngineConfig + Backend. */
        private fun litertLm(model: File, useNpu: Boolean, nativeLibDir: String): LlmEngine? {
            return try {
                val backendCls = Class.forName("com.google.ai.edge.litert.Backend")
                val backend = if (useNpu) {
                    backendCls.getMethod("NPU", String::class.java).invoke(null, nativeLibDir)
                } else {
                    backendCls.getMethod("GPU").invoke(null)
                }
                val cfgCls = Class.forName("com.google.ai.edge.litert.lm.EngineConfig")
                val cfg = cfgCls
                    .getConstructor(String::class.java, backendCls)
                    .newInstance(model.absolutePath, backend)
                val engineCls = Class.forName("com.google.ai.edge.litert.lm.Engine")
                val engine = engineCls.getConstructor(cfgCls).newInstance(cfg)
                Log.i(TAG, "LiteRT-LM engine up (backend=${if (useNpu) "NPU" else "GPU"})")

                LlmEngine(
                    impl = engine,
                    generateFn = { e, prompt, onToken ->
                        // Prefer a streaming overload so TTFT is real; else one-shot.
                        val streaming = e.javaClass.methods.firstOrNull {
                            it.name == "generate" && it.parameterTypes.size == 2
                        }
                        if (streaming != null) {
                            val sb = StringBuilder()
                            val cb = java.lang.reflect.Proxy.newProxyInstance(
                                e.javaClass.classLoader,
                                arrayOf(streaming.parameterTypes[1])
                            ) { _, _, args ->
                                val tok = args?.firstOrNull()?.toString().orEmpty()
                                sb.append(tok)
                                onToken(tok)
                                null
                            }
                            streaming.invoke(e, prompt, cb)
                            sb.toString()
                        } else {
                            val one = e.javaClass.getMethod("generate", String::class.java)
                            val out = one.invoke(e, prompt)?.toString().orEmpty()
                            onToken(out)
                            out
                        }
                    },
                    closeFn = { e ->
                        runCatching { e.javaClass.getMethod("close").invoke(e) }
                            .onFailure { Log.w(TAG, "close: ${it.message}") }
                    },
                )
            } catch (t: Throwable) {
                Log.i(TAG, "LiteRT-LM not usable (${t.javaClass.simpleName}: ${t.message})")
                null
            }
        }

        /**
         * Fallback runtime: MediaPipe LlmInference, which also loads .litertlm and
         * sits on LiteRT underneath. Still an honest `litert-gpu` badge — we ask for
         * and get the GPU backend; only the wrapper differs.
         */
        private fun mediaPipe(ctx: Context, model: File): LlmEngine? {
            return try {
                val optCls = Class.forName(
                    "com.google.mediapipe.tasks.genai.llminference.LlmInference\$LlmInferenceOptions")
                val builder = optCls.getMethod("builder").invoke(null)
                builder.javaClass.getMethod("setModelPath", String::class.java)
                    .invoke(builder, model.absolutePath)
                runCatching {
                    val backendCls = Class.forName(
                        "com.google.mediapipe.tasks.genai.llminference.LlmInference\$Backend")
                    val gpu = backendCls.getField("GPU").get(null)
                    builder.javaClass.getMethod("setPreferredBackend", backendCls)
                        .invoke(builder, gpu)
                }
                val options = builder.javaClass.getMethod("build").invoke(builder)
                val llmCls = Class.forName(
                    "com.google.mediapipe.tasks.genai.llminference.LlmInference")
                val llm = llmCls.getMethod("createFromOptions", Context::class.java, optCls)
                    .invoke(null, ctx, options)
                Log.i(TAG, "MediaPipe LlmInference engine up (GPU)")

                LlmEngine(
                    impl = llm!!,
                    generateFn = { e, prompt, onToken ->
                        val out = e.javaClass.getMethod("generateResponse", String::class.java)
                            .invoke(e, prompt)?.toString().orEmpty()
                        onToken(out)
                        out
                    },
                    closeFn = { e ->
                        runCatching { e.javaClass.getMethod("close").invoke(e) }
                            .onFailure { Log.w(TAG, "close: ${it.message}") }
                    },
                )
            } catch (t: Throwable) {
                Log.i(TAG, "MediaPipe genai not usable (${t.javaClass.simpleName})")
                null
            }
        }
    }
}
