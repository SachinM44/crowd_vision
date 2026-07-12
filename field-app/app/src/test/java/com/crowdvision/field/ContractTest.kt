package com.crowdvision.field

import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.File

/**
 * Contract tests for the officer node — no phone required.
 *
 * These run the SAME Envelope/Schema/KeywordStructurer code the app ships, and
 * dump every produced message to build/contract-out/officer_messages.json so the
 * real Python validator (crowdvision._lib.messages.validate_envelope) can check
 * them. A green Kotlin test that emits a payload the broker would reject is
 * worthless — so the Python side is the actual gate.
 *
 *   gradle :app:test
 *   python tools/check_field_contract.py     (validates the dumped JSON)
 */
class ContractTest {

    private fun payloadsOut(): File =
        File("build/contract-out").apply { mkdirs() }.let { File(it, "officer_messages.json") }

    @Test
    fun `envelope has the v9 section-e shape`() {
        val env = Envelope.build(
            Envelope.T_OFFICER_BEACON, "officer-1",
            JSONObject().put("officer_id", "officer-1")
        )
        assertEquals("officer.beacon", env.getString("type"))
        assertEquals(1, env.getInt("v"))
        assertEquals("officer-1", env.getString("src"))
        assertTrue("seq must be an int", env.get("seq") is Int)
        assertTrue(env.get("payload") is JSONObject)
        // IST with milliseconds, e.g. 2026-07-12T07:41:03.214+05:30
        val ts = env.getString("ts")
        assertTrue("ts must be ISO-8601 IST w/ ms: $ts",
            Regex("""\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}\+05:30""").matches(ts))
    }

    @Test
    fun `seq is monotonic`() {
        val a = Envelope.build(Envelope.T_HEARTBEAT, "officer-1", JSONObject()).getInt("seq")
        val b = Envelope.build(Envelope.T_HEARTBEAT, "officer-1", JSONObject()).getInt("seq")
        assertTrue("seq must increase: $a -> $b", b > a)
    }

    @Test
    fun `schema gate rejects bad structures`() {
        assertFalse(Schema.validate(null))
        assertFalse("bad type",
            Schema.validate(StructuredIncident("catastrophe", "gate 3", "high", listOf("medic"))))
        assertFalse("bad severity",
            Schema.validate(StructuredIncident("medical", "gate 3", "extreme", listOf("medic"))))
        assertFalse("empty needs",
            Schema.validate(StructuredIncident("medical", "gate 3", "high", emptyList())))
        assertFalse("blank location",
            Schema.validate(StructuredIncident("medical", "  ", "high", listOf("medic"))))
        assertTrue(Schema.validate(StructuredIncident("medical", "gate 3", "high", listOf("medic"))))
    }

    @Test
    fun `parser handles the shapes FunctionGemma actually emits`() {
        // 1. tool_call JSON with a parameters wrapper
        val a = Schema.parse(
            """<tool_call>{"name":"report_incident","parameters":{"type":"medical",
               "location_hint":"Gate 3","severity":"high","needs":["medic","stretcher"]}}</tool_call>"""
        )
        assertEquals("medical", a?.type)
        assertEquals(listOf("medic", "stretcher"), a?.needs)

        // 2. python-style tool_code call
        val b = Schema.parse(
            """```tool_code
               print(report_incident(type="crush-risk", location_hint="Gate 2",
                     severity="high", needs=["crowd-control"]))
               ```"""
        )
        assertEquals("crush-risk", b?.type)
        assertEquals("Gate 2", b?.locationHint)
        assertEquals(listOf("crowd-control"), b?.needs)

        // 3. bare JSON
        val c = Schema.parse("""{"type":"fire","location_hint":"zone D","severity":"medium","needs":["fire-team"]}""")
        assertEquals("fire", c?.type)

        // 4. garbage -> null -> schema-invalid -> NO-OP (never published)
        assertFalse(Schema.validate(Schema.parse("I think someone might be hurt somewhere")))
    }

    @Test
    fun `keyword structurer produces valid structures and honest badges`() {
        val k = KeywordStructurer()
        val cases = mapOf(
            "man collapsed near gate 2 barrier, crowd gathering" to "medical",
            "crowd crushing against the barrier at gate 3" to "crush-risk",
            "smoke coming from behind the food stall in zone D" to "fire",
            "fight broke out near gate 1, two men" to "security",
            "lost child near the ferris wheel" to "lost-person",
        )
        for ((text, expectedType) in cases) {
            val r = k.structure(text)
            assertTrue("must be schema-valid: $text", r.schemaValid)
            assertEquals("type for: $text", expectedType, r.structured!!.type)
            // Badges never lie: no model ran here.
            assertEquals("keyword-rules", r.modelId)
            assertEquals(Envelope.BACKEND_CPU, r.backend)
        }
    }

    /**
     * Emit one of every message the officer publishes, exactly as FieldService
     * builds it, so Python can validate the real bytes.
     */
    @Test
    fun `dump every officer message for the python validator`() {
        val id = "officer-1"
        val out = JSONArray()

        // 1. beacon (available)
        out.put(Envelope.build(Envelope.T_OFFICER_BEACON, id, JSONObject()
            .put("officer_id", id).put("lat", 12.9699).put("lon", 77.7501)
            .put("accuracy_m", 5.0).put("status", "available")
            .put("battery_pct", 84).put("ack_dispatch_id", JSONObject.NULL)))

        // 2. beacon (the ACK: enroute + ack_dispatch_id)
        out.put(Envelope.build(Envelope.T_OFFICER_BEACON, id, JSONObject()
            .put("officer_id", id).put("lat", 12.9699).put("lon", 77.7501)
            .put("accuracy_m", 5.0).put("status", "enroute")
            .put("battery_pct", 84).put("ack_dispatch_id", "dsp-1")))

        // 3. incident from the model path (badges as if FunctionGemma ran)
        val s = StructuredIncident("medical", "Gate 3", "high", listOf("medic", "stretcher"))
        out.put(Envelope.build(Envelope.T_INCIDENT_REPORT, id, JSONObject()
            .put("incident_id", "inc-abc123").put("officer_id", id)
            .put("lat", 12.9699).put("lon", 77.7501)
            .put("text", "man collapsed near gate 3")
            .put("structured", s.toJson()).put("schema_valid", true)
            .put("photo_ref", JSONObject.NULL)
            .put("model_id", Models.FUNCTIONGEMMA_ID)
            .put("inference_backend", Envelope.BACKEND_LITERT_GPU)
            .put("latency_ms", 412).put("ttft_ms", 96)))

        // 4. incident from the dropdown-form fallback (honest zero-AI badges)
        out.put(Envelope.build(Envelope.T_INCIDENT_REPORT, id, JSONObject()
            .put("incident_id", "inc-def456").put("officer_id", id)
            .put("lat", 12.9699).put("lon", 77.7501)
            .put("text", "form report: medical @ Gate 3")
            .put("structured", s.toJson()).put("schema_valid", true)
            .put("photo_ref", JSONObject.NULL)
            .put("model_id", "dropdown-form")
            .put("inference_backend", Envelope.BACKEND_CPU)
            .put("latency_ms", 0).put("ttft_ms", 0)))

        // 5. heartbeats: online + the LWT payload
        out.put(Envelope.build(Envelope.T_HEARTBEAT, id, JSONObject()
            .put("device", id).put("state", "online")))
        out.put(Envelope.build(Envelope.T_HEARTBEAT, id, JSONObject()
            .put("device", id).put("state", "offline").put("reason", "lwt")))

        payloadsOut().writeText(out.toString(2))
        assertEquals(6, out.length())
    }
}
