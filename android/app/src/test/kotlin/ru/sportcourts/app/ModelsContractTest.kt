package ru.sportcourts.app

import kotlinx.serialization.KSerializer
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.jsonObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertTrue
import org.junit.Test
import ru.sportcourts.app.data.*

/**
 * Проверяет, что модели приложения разбирают настоящие ответы сервера.
 * Образцы (server_samples.json) сняты с работающего сервера во время разработки;
 * при изменении API их нужно обновить.
 */
class ModelsContractTest {
    private val json = Json {
        ignoreUnknownKeys = true
        explicitNulls = false
        coerceInputValues = true
    }

    private val samples: JsonObject = json.parseToJsonElement(
        javaClass.classLoader!!.getResourceAsStream("server_samples.json")!!.bufferedReader(Charsets.UTF_8).readText()
    ).jsonObject

    private fun <T> decode(key: String, serializer: KSerializer<T>): T {
        val element = samples[key] ?: error("Нет образца $key")
        return json.decodeFromJsonElement(serializer, element)
    }

    @Test
    fun allSamplesDecode() {
        decode("AuthResponse", AuthResponse.serializer())
        decode("Me", Me.serializer())
        decode("Me.patch", Me.serializer())
        decode("avatar", Me.serializer())
        decode("SportsResponse", SportsResponse.serializer())
        decode("UsersResponse", UsersResponse.serializer())
        decode("UserProfile", UserProfile.serializer())
        decode("UserProfile.friend", UserProfile.serializer())
        decode("FriendRequestResult", FriendRequestResult.serializer())
        decode("FriendRequestsResponse", FriendRequestsResponse.serializer())
        decode("FriendsResponse", FriendsResponse.serializer())
        decode("VenuesResponse", VenuesResponse.serializer())
        decode("Venue", Venue.serializer())
        decode("Venue.present", Venue.serializer())
        decode("PresenceResult", PresenceResult.serializer())
        decode("PlayerReportResult", PlayerReportResult.serializer())
        decode("PlayerReportsResponse", PlayerReportsResponse.serializer())
        decode("DuplicatesResponse", DuplicatesResponse.serializer())
        decode("UploadResult", UploadResult.serializer())
        decode("SubmissionsResponse", SubmissionsResponse.serializer())
        decode("SubmissionsResponse.mod", SubmissionsResponse.serializer())
        decode("ProposalsResponse", ProposalsResponse.serializer())
        decode("ProposalsResponse.mod", ProposalsResponse.serializer())
        decode("DecisionsResponse", DecisionsResponse.serializer())
        decode("Game", Game.serializer())
        decode("GamesResponse", GamesResponse.serializer())
        decode("InviteResult", InviteResult.serializer())
        decode("Message", Message.serializer())
        decode("MessagesResponse", MessagesResponse.serializer())
        decode("ConversationsResponse", ConversationsResponse.serializer())
        decode("NotificationsResponse", NotificationsResponse.serializer())
        decode("UnreadCounts", UnreadCounts.serializer())
        decode("BlocksResponse", BlocksResponse.serializer())
        decode("ModeratorRequestsResponse", ModeratorRequestsResponse.serializer())
        decode("AdminUsersResponse", AdminUsersResponse.serializer())
        decode("AdminReportsResponse", AdminReportsResponse.serializer())
        decode("AuditResponse", AuditResponse.serializer())
        decode("SystemStatus", SystemStatus.serializer())
        decode("TempPassword", TempPassword.serializer())
    }

    @Test
    fun venueFieldsAreMapped() {
        val v = decode("Venue.present", Venue.serializer())
        assertEquals("Хамовники Арена", v.name)
        assertEquals("outdoor", v.venueType)
        assertEquals(true, v.myPresence?.active)
        assertNotNull(v.myPresence?.expiresAt)
        assertEquals("Баскетбол", v.sports.first().name)
    }

    @Test
    fun gameSeatsAreMapped() {
        val g = decode("Game", Game.serializer())
        assertEquals(4, g.maxPlayers)
        assertEquals(1, g.participantsCount)
        assertEquals(3, g.freeSlots)
        assertTrue(g.isOrganizer && g.joined)
        assertTrue(g.participants.first().isOrganizer)
    }

    @Test
    fun errorEnvelopeDecodesAndToleratesDetails() {
        val body = """{"error":{"code":"game_full","message":"Мест нет","details":{"free":0}}}"""
        val e = json.decodeFromString(ErrorEnvelope.serializer(), body).error
        assertEquals("game_full", e?.code)
        assertEquals("Мест нет", e?.message)
        val minimal = json.decodeFromString(ErrorEnvelope.serializer(), """{"error":{"code":"x","message":"y"}}""").error
        assertEquals("y", minimal?.message)
    }

    @Test
    fun roleHelpers() {
        val me = decode("Me", Me.serializer())
        assertTrue(!me.isModerator && !me.isAdmin)
        assertTrue(me.copy(role = "admin").canSeeReports)
        assertTrue(!me.copy(role = "moderator").canSeeReports)
        assertTrue(me.copy(role = "moderator", canReviewReports = true).canSeeReports)
    }
}
