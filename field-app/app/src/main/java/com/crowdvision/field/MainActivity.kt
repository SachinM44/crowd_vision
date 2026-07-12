package com.crowdvision.field

import android.Manifest
import android.app.Activity
import android.content.Intent
import android.content.pm.PackageManager
import android.net.Uri
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.widget.ArrayAdapter
import android.widget.Button
import android.widget.EditText
import android.widget.Spinner
import android.widget.TextView
import android.widget.Toast
import androidx.appcompat.app.AppCompatActivity
import androidx.core.app.ActivityCompat
import androidx.core.content.ContextCompat
import java.io.File

/**
 * One screen: connect, see dispatches, report an incident.
 *
 * The incident box has BOTH paths on the same screen (BETA_HANDOFF §4H):
 *   "Structure + send" -> FunctionGemma (or keyword rules) -> schema gate
 *   "Send form report" -> zero-AI dropdown fallback, badged dropdown-form/cpu
 * A schema-invalid model output is never published; the form is right there.
 */
class MainActivity : AppCompatActivity() {

    private val ui = Handler(Looper.getMainLooper())
    private var structurer: IncidentStructurer? = null
    private val stateListener: () -> Unit = { ui.post { render() } }

    private lateinit var brokerHost: EditText
    private lateinit var officerId: EditText
    private lateinit var statusView: TextView
    private lateinit var dispatchView: TextView
    private lateinit var incidentText: EditText
    private lateinit var aiResultView: TextView
    private lateinit var benchView: TextView
    private lateinit var spinnerType: Spinner
    private lateinit var spinnerSeverity: Spinner
    private lateinit var formLocation: EditText
    private lateinit var formNeeds: EditText

    companion object {
        private const val REQ_PERMS = 1001
        private const val REQ_PICK_MODEL = 1002
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_main)
        AppState.load(this)

        brokerHost = findViewById(R.id.brokerHost)
        officerId = findViewById(R.id.officerId)
        statusView = findViewById(R.id.statusView)
        dispatchView = findViewById(R.id.dispatchView)
        incidentText = findViewById(R.id.incidentText)
        aiResultView = findViewById(R.id.aiResultView)
        benchView = findViewById(R.id.benchView)
        spinnerType = findViewById(R.id.spinnerType)
        spinnerSeverity = findViewById(R.id.spinnerSeverity)
        formLocation = findViewById(R.id.formLocation)
        formNeeds = findViewById(R.id.formNeeds)

        brokerHost.setText(AppState.brokerHost)
        officerId.setText(AppState.officerId)
        spinnerType.adapter = ArrayAdapter(
            this, android.R.layout.simple_spinner_dropdown_item, INCIDENT_TYPES)
        spinnerSeverity.adapter = ArrayAdapter(
            this, android.R.layout.simple_spinner_dropdown_item, SEVERITIES)

        findViewById<Button>(R.id.btnGoOnDuty).setOnClickListener { goOnDuty() }
        findViewById<Button>(R.id.btnOffDuty).setOnClickListener { goOffDuty() }
        findViewById<Button>(R.id.btnClearDispatch).setOnClickListener {
            FieldService.instance?.clearDispatch()
        }
        findViewById<Button>(R.id.btnStructureSend).setOnClickListener { structureAndSend() }
        findViewById<Button>(R.id.btnFormSend).setOnClickListener { sendForm() }
        findViewById<Button>(R.id.btnImportModel).setOnClickListener { importModel() }
        findViewById<Button>(R.id.btnBench).setOnClickListener { runBench() }
        findViewById<Button>(R.id.btnE2bProbe).setOnClickListener { runE2bProbe() }

        AppState.addListener(stateListener)
        render()
    }

    override fun onDestroy() {
        AppState.removeListener(stateListener)
        structurer?.close()
        super.onDestroy()
    }

    // -- duty ----------------------------------------------------------------
    private fun goOnDuty() {
        AppState.brokerHost = brokerHost.text.toString().trim().ifEmpty { "127.0.0.1" }
        AppState.officerId = officerId.text.toString().trim().ifEmpty { "officer-1" }
        AppState.save(this)

        val needed = mutableListOf(Manifest.permission.ACCESS_FINE_LOCATION)
        if (android.os.Build.VERSION.SDK_INT >= 33) {
            needed.add(Manifest.permission.POST_NOTIFICATIONS)
        }
        val missing = needed.filter {
            ContextCompat.checkSelfPermission(this, it) != PackageManager.PERMISSION_GRANTED
        }
        if (missing.isNotEmpty()) {
            ActivityCompat.requestPermissions(this, missing.toTypedArray(), REQ_PERMS)
            return
        }
        startForegroundService(Intent(this, FieldService::class.java))
        AppState.setEvent("on duty as ${AppState.officerId} -> ${AppState.brokerHost}")
    }

    override fun onRequestPermissionsResult(
        requestCode: Int, permissions: Array<out String>, grantResults: IntArray,
    ) {
        super.onRequestPermissionsResult(requestCode, permissions, grantResults)
        if (requestCode != REQ_PERMS) return
        val fineIdx = permissions.indexOf(Manifest.permission.ACCESS_FINE_LOCATION)
        if (fineIdx >= 0 && grantResults.getOrNull(fineIdx) != PackageManager.PERMISSION_GRANTED) {
            toast("Location is required — beacons cannot be faked")
            return
        }
        goOnDuty()
    }

    private fun goOffDuty() {
        stopService(Intent(this, FieldService::class.java))
        AppState.setEvent("off duty")
    }

    // -- incident: AI path ---------------------------------------------------
    private fun structurer(): IncidentStructurer =
        structurer ?: StructurerFactory.best(this).also { structurer = it }

    private fun structureAndSend() {
        val text = incidentText.text.toString().trim()
        if (text.isEmpty()) {
            toast("Type what you see")
            return
        }
        val svc = FieldService.instance
        if (svc == null) {
            toast("Go on duty first")
            return
        }
        aiResultView.text = "structuring…"
        Thread {
            val r = try {
                structurer().structure(text)
            } catch (t: Throwable) {
                StructureResult(null, false, "error", Envelope.BACKEND_CPU, 0, 0,
                    raw = t.message ?: "structurer crashed")
            }
            val published = if (r.schemaValid) svc.publishIncident(text, r, null) else false
            ui.post {
                aiResultView.text = buildString {
                    append("model=${r.modelId}  backend=${r.backend}\n")
                    append("ttft=${r.ttftMs}ms  latency=${r.latencyMs}ms\n")
                    append("schema_valid=${r.schemaValid}\n")
                    r.structured?.let { append(it.toJson().toString()) }
                    if (!published) append("\nNOT PUBLISHED — use the form below.")
                }
                if (published) incidentText.setText("")
            }
        }.start()
    }

    // -- incident: zero-AI fallback -----------------------------------------
    private fun sendForm() {
        val svc = FieldService.instance
        if (svc == null) {
            toast("Go on duty first")
            return
        }
        val needs = formNeeds.text.toString().split(",")
            .map { it.trim() }.filter { it.isNotEmpty() }
            .ifEmpty { listOf("steward") }
        val s = StructuredIncident(
            type = spinnerType.selectedItem as String,
            locationHint = formLocation.text.toString().trim().ifEmpty { "officer position" },
            severity = spinnerSeverity.selectedItem as String,
            needs = needs,
        )
        // Honest badges for the no-model path (§4H).
        val r = StructureResult(
            structured = s, schemaValid = Schema.validate(s),
            modelId = "dropdown-form", backend = Envelope.BACKEND_CPU,
            latencyMs = 0, ttftMs = 0,
        )
        val text = incidentText.text.toString().trim()
            .ifEmpty { "form report: ${s.type} @ ${s.locationHint}" }
        if (svc.publishIncident(text, r, null)) {
            toast("Form report sent")
            incidentText.setText("")
        }
    }

    // -- model import (SAF; works even where adb cannot write Android/data) ---
    private fun importModel() {
        val i = Intent(Intent.ACTION_OPEN_DOCUMENT).apply {
            addCategory(Intent.CATEGORY_OPENABLE)
            type = "*/*"
        }
        startActivityForResult(i, REQ_PICK_MODEL)
    }

    @Deprecated("startActivityForResult is fine for a single hackathon picker")
    override fun onActivityResult(requestCode: Int, resultCode: Int, data: Intent?) {
        super.onActivityResult(requestCode, resultCode, data)
        if (requestCode != REQ_PICK_MODEL || resultCode != Activity.RESULT_OK) return
        val uri: Uri = data?.data ?: return
        Thread {
            val dest = File(getExternalFilesDir("models"), Models.FUNCTIONGEMMA)
            try {
                dest.parentFile?.mkdirs()
                contentResolver.openInputStream(uri)!!.use { input ->
                    dest.outputStream().use { out -> input.copyTo(out) }
                }
                structurer?.close()
                structurer = null                     // rebuild with the model present
                ui.post { toast("Model imported: ${dest.length() / (1024 * 1024)} MB") }
            } catch (t: Throwable) {
                ui.post { toast("Import failed: ${t.message}") }
            }
        }.start()
    }

    // -- benches -------------------------------------------------------------
    private fun runBench() {
        benchView.text = "bench running…"
        Thread {
            val path = Bench.runFunctionGemmaBench(this, structurer())
            ui.post { benchView.text = "bench written:\n$path" }
        }.start()
    }

    private fun runE2bProbe() {
        benchView.text = "E2B probe running (benchmark only)…"
        Thread {
            val out = Bench.runE2bProbe(this)
            ui.post { benchView.text = out }
        }.start()
    }

    // -- render --------------------------------------------------------------
    private fun render() {
        val pos = if (AppState.lat != null)
            "%.5f, %.5f (±%.0fm)".format(AppState.lat, AppState.lon, AppState.accuracyM)
        else "no GPS fix yet"
        statusView.text = buildString {
            append(if (AppState.connected) "● broker connected" else "○ broker offline")
            append("   status=${AppState.status}\n")
            append("gps: $pos\n")
            append("llm: ${if (BuildConfig.WITH_LLM) "FunctionGemma build" else "keyword-rules build"}\n")
            append("last: ${AppState.lastEvent}")
        }
        dispatchView.text = AppState.ackDispatchId?.let {
            "DISPATCH $it\n${AppState.lastDispatchReason ?: ""}\nacked — status enroute"
        } ?: "No active dispatch"
    }

    private fun toast(m: String) = Toast.makeText(this, m, Toast.LENGTH_SHORT).show()
}
