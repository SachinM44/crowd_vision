package com.crowdvision.field

import org.json.JSONObject
import org.junit.Assert.assertTrue
import org.junit.Assume.assumeTrue
import org.junit.Test
import java.net.InetSocketAddress
import java.net.Socket
import java.util.concurrent.CountDownLatch
import java.util.concurrent.TimeUnit

/**
 * Runs the SHIPPED Mqtt.kt + OfficerLogic against a REAL broker — no phone.
 *
 * This is the test that would have caught a wrong topic, a missing LWT, or an
 * ack that never fires. Paho's Java client is the same client the APK ships, so
 * everything below the Android UI is exercised for real.
 *
 * Skipped automatically when no broker is listening, so `gradle test` stays
 * green offline. To run it:
 *     python -m crowdvision.sim --all --real-officers officer-1,officer-2
 *     cd field-app && gradle :app:testDebugUnitTest --tests '*MqttLiveTest'
 *
 * BOTH officer slots are reserved on purpose. The sim's officer-2 sits exactly
 * ON the demo incident, so nearest-officer selection would always pick it over
 * a real phone (that is correct behaviour, and it is what the two-dot demo
 * shows). Reserving both slots leaves this client as the only officer on the
 * mesh, which is what makes the dispatch -> ack loop assertable here.
 */
class MqttLiveTest {

    private val host = System.getProperty("cv.broker") ?: "127.0.0.1"
    private val port = (System.getProperty("cv.broker.port") ?: "1883").toInt()
    private val officerId = "officer-1"

    private fun brokerUp(): Boolean = try {
        Socket().use { it.connect(InetSocketAddress(host, port), 800); true }
    } catch (t: Throwable) {
        false
    }

    @Test
    fun `officer connects, beacons, and acks a dispatch through the real client`() {
        assumeTrue("no broker on $host:$port — skipping live test", brokerUp())

        val dispatched = CountDownLatch(1)
        var acked: JSONObject? = null
        var status = "available"
        var ackId: String? = null

        val mqtt = Mqtt(officerId, host, port) { env ->
            // Exactly what FieldService does: parse, flip to enroute, beacon back.
            OfficerLogic.parseDispatch(env, officerId)?.let { d ->
                status = "enroute"
                ackId = d.dispatchId
                dispatched.countDown()
            }
        }
        mqtt.connect()

        // Wait for CONNACK (connectComplete subscribes + sends the online heartbeat).
        val start = System.currentTimeMillis()
        while (!mqtt.isConnected && System.currentTimeMillis() - start < 10_000) {
            Thread.sleep(100)
        }
        assertTrue("client never connected to $host:$port", mqtt.isConnected)

        // Beacon as "available" so the decider knows where we are. Keep beaconing
        // on a 3 s cadence exactly like FieldService does, for the whole wait.
        fun beacon() = mqtt.publish(
            Envelope.topicOfficerBeacon(officerId), Envelope.T_OFFICER_BEACON,
            OfficerLogic.beaconPayload(officerId, 12.9699, 77.7501, 5.0,
                status, 84, ackId),
            qos = 0,
        )
        val beaconing = Thread {
            while (!Thread.currentThread().isInterrupted) {
                beacon()
                try {
                    Thread.sleep(3000)
                } catch (ie: InterruptedException) {
                    return@Thread
                }
            }
        }.apply { isDaemon = true; start() }

        // The sim's decider dispatches on RED. The surge cycles ~45 s, so allow
        // a full cycle plus slack.
        val got = dispatched.await(75, TimeUnit.SECONDS)
        beaconing.interrupt()
        assertTrue("no dispatch.order arrived on ${Envelope.topicDispatch(officerId)} " +
            "within 75s — is the sim running with --real-officers $officerId ?", got)

        // The ack IS a beacon carrying ack_dispatch_id (§4G).
        beacon()
        acked = OfficerLogic.beaconPayload(officerId, 12.9699, 77.7501, 5.0,
            status, 84, ackId)
        Thread.sleep(500)
        mqtt.disconnect()

        assertTrue("status must flip to enroute", acked!!.getString("status") == "enroute")
        assertTrue("ack beacon must carry ack_dispatch_id",
            acked!!.optString("ack_dispatch_id").startsWith("dsp-"))
        println("LIVE OK: dispatch ${acked!!.optString("ack_dispatch_id")} acked as enroute")
    }
}
