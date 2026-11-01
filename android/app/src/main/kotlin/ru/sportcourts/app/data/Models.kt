package ru.sportcourts.app.data

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

// Модели соответствуют ответам сервера (см. docs/API.md). Неизвестные поля игнорируются.

@Serializable
data class Sport(
    val id: Int,
    val code: String = "",
    val name: String,
    @SerialName("is_active") val isActive: Boolean = true,
)

@Serializable
data class Me(
    val id: Long,
    val login: String,
    @SerialName("display_name") val displayName: String,
    @SerialName("avatar_url") val avatarUrl: String? = null,
    val role: String = "user",
    @SerialName("can_review_reports") val canReviewReports: Boolean = false,
    @SerialName("must_change_password") val mustChangePassword: Boolean = false,
    @SerialName("favorite_sports") val favoriteSports: List<Sport> = emptyList(),
) {
    val isModerator get() = role == "moderator" || role == "admin"
    val isAdmin get() = role == "admin"
    val canSeeReports get() = isAdmin || (role == "moderator" && canReviewReports)
}

@Serializable
data class AuthResponse(val token: String, val user: Me)

@Serializable
data class UserBrief(
    val id: Long,
    val login: String = "",
    @SerialName("display_name") val displayName: String = "",
    @SerialName("avatar_url") val avatarUrl: String? = null,
    @SerialName("favorite_sports") val favoriteSports: List<Sport> = emptyList(),
    /** none | friend | request_sent | request_received (только в результатах поиска) */
    val relation: String? = null,
)

@Serializable
data class UserProfile(
    val id: Long,
    val login: String,
    @SerialName("display_name") val displayName: String,
    @SerialName("avatar_url") val avatarUrl: String? = null,
    @SerialName("favorite_sports") val favoriteSports: List<Sport> = emptyList(),
    @SerialName("is_friend") val isFriend: Boolean = false,
    @SerialName("blocked_by_me") val blockedByMe: Boolean = false,
    @SerialName("is_self") val isSelf: Boolean = false,
    val online: Boolean? = null,
    @SerialName("last_seen_at") val lastSeenAt: String? = null,
)

@Serializable
data class Friend(
    val id: Long,
    val login: String = "",
    @SerialName("display_name") val displayName: String = "",
    @SerialName("avatar_url") val avatarUrl: String? = null,
    val online: Boolean = false,
    @SerialName("last_seen_at") val lastSeenAt: String? = null,
    @SerialName("unread_messages") val unreadMessages: Int = 0,
    val activity: String? = null,
)

@Serializable data class FriendsResponse(val items: List<Friend>)

@Serializable
data class FriendRequestItem(val id: Long, @SerialName("created_at") val createdAt: String, val user: UserBrief)

@Serializable data class FriendRequestsResponse(val items: List<FriendRequestItem>)
@Serializable data class FriendRequestResult(val status: String, @SerialName("request_id") val requestId: Long)
@Serializable data class UsersResponse(val items: List<UserBrief>)
@Serializable data class SportsResponse(val items: List<Sport>)

// ---------------------------------------------------------------- площадки
@Serializable
data class LatestReport(
    @SerialName("player_count") val playerCount: Int,
    @SerialName("reported_at") val reportedAt: String,
    @SerialName("is_fresh") val isFresh: Boolean = true,
)

@Serializable
data class MyPresence(val active: Boolean = false, @SerialName("expires_at") val expiresAt: String? = null)

@Serializable
data class Venue(
    val id: Long,
    val name: String,
    val address: String,
    val latitude: Double,
    val longitude: Double,
    @SerialName("venue_type") val venueType: String,
    @SerialName("work_hours") val workHours: String? = null,
    @SerialName("cost_info") val costInfo: String? = null,
    @SerialName("photo_url") val photoUrl: String? = null,
    val sports: List<Sport> = emptyList(),
    @SerialName("checked_in_count") val checkedInCount: Int = 0,
    @SerialName("latest_report") val latestReport: LatestReport? = null,
    @SerialName("open_games_count") val openGamesCount: Int = 0,
    @SerialName("distance_km") val distanceKm: Double? = null,
    val status: String = "active",
    @SerialName("players_estimate") val playersEstimate: Int? = null,
    val description: String? = null,
    @SerialName("my_presence") val myPresence: MyPresence? = null,
)

@Serializable
data class VenuesResponse(val items: List<Venue>, val total: Int = 0, val limit: Int = 0, val offset: Int = 0)

@Serializable
data class PresenceResult(
    val active: Boolean,
    @SerialName("expires_at") val expiresAt: String? = null,
    @SerialName("checked_in_count") val checkedInCount: Int = 0,
)

@Serializable
data class PlayerReportItem(
    val id: Long,
    @SerialName("player_count") val playerCount: Int,
    @SerialName("reported_at") val reportedAt: String,
    val reporter: UserBrief,
)

@Serializable data class PlayerReportsResponse(val items: List<PlayerReportItem>)
@Serializable data class PlayerReportBody(@SerialName("player_count") val playerCount: Int)

@Serializable
data class PlayerReportResult(val id: Long, @SerialName("player_count") val playerCount: Int, @SerialName("reported_at") val reportedAt: String)

@Serializable
data class VenueBody(
    val name: String,
    val address: String,
    val latitude: Double,
    val longitude: Double,
    @SerialName("venue_type") val venueType: String,
    @SerialName("sport_ids") val sportIds: List<Int>,
    val description: String? = null,
    @SerialName("work_hours") val workHours: String? = null,
    @SerialName("cost_info") val costInfo: String? = null,
    @SerialName("photo_token") val photoToken: String? = null,
    val force: Boolean = false,
)

@Serializable data class UploadResult(val token: String)

@Serializable
data class Duplicate(val kind: String, val id: Long, val name: String, val address: String, @SerialName("distance_m") val distanceM: Int)

@Serializable data class DuplicatesResponse(val duplicates: List<Duplicate>)

@Serializable
data class VenueSnapshot(
    val name: String = "",
    val address: String = "",
    val latitude: Double = 0.0,
    val longitude: Double = 0.0,
    @SerialName("venue_type") val venueType: String = "outdoor",
    val description: String? = null,
    @SerialName("work_hours") val workHours: String? = null,
    @SerialName("cost_info") val costInfo: String? = null,
    @SerialName("photo_url") val photoUrl: String? = null,
    val sports: List<Sport> = emptyList(),
)

@Serializable
data class Submission(
    val id: Long,
    val name: String,
    val address: String,
    val latitude: Double,
    val longitude: Double,
    @SerialName("venue_type") val venueType: String,
    val description: String? = null,
    @SerialName("work_hours") val workHours: String? = null,
    @SerialName("cost_info") val costInfo: String? = null,
    @SerialName("photo_url") val photoUrl: String? = null,
    val status: String,
    @SerialName("decision_reason") val decisionReason: String? = null,
    @SerialName("decided_at") val decidedAt: String? = null,
    @SerialName("created_at") val createdAt: String,
    @SerialName("venue_id") val venueId: Long? = null,
    val sports: List<Sport> = emptyList(),
    val submitter: UserBrief? = null,
    val duplicates: List<Duplicate> = emptyList(),
)

@Serializable data class SubmissionsResponse(val items: List<Submission>)

@Serializable
data class Proposal(
    val id: Long,
    @SerialName("venue_id") val venueId: Long,
    val name: String,
    val address: String,
    val latitude: Double,
    val longitude: Double,
    @SerialName("venue_type") val venueType: String,
    val description: String? = null,
    @SerialName("work_hours") val workHours: String? = null,
    @SerialName("cost_info") val costInfo: String? = null,
    @SerialName("photo_url") val photoUrl: String? = null,
    val status: String,
    @SerialName("decision_reason") val decisionReason: String? = null,
    @SerialName("decided_at") val decidedAt: String? = null,
    @SerialName("created_at") val createdAt: String,
    val sports: List<Sport> = emptyList(),
    val proposer: UserBrief? = null,
    val current: VenueSnapshot = VenueSnapshot(),
)

@Serializable data class ProposalsResponse(val items: List<Proposal>)
@Serializable data class CreatedResult(val id: Long = 0, val status: String = "")
@Serializable data class RejectBody(val reason: String)

@Serializable
data class ModerationDecision(
    val id: Long,
    val kind: String,
    val decision: String,
    val reason: String? = null,
    @SerialName("created_at") val createdAt: String,
    @SerialName("venue_name") val venueName: String? = null,
    val moderator: UserBrief? = null,
)

@Serializable data class DecisionsResponse(val items: List<ModerationDecision>)

// ---------------------------------------------------------------- игры
@Serializable
data class GameVenue(val id: Long, val name: String, val address: String = "", val sports: List<Sport> = emptyList())

@Serializable
data class Participant(
    val user: UserBrief,
    @SerialName("joined_at") val joinedAt: String = "",
    @SerialName("is_organizer") val isOrganizer: Boolean = false,
)

@Serializable
data class Game(
    val id: Long,
    val title: String,
    @SerialName("starts_at") val startsAt: String,
    @SerialName("max_players") val maxPlayers: Int,
    val status: String,
    val venue: GameVenue,
    val organizer: UserBrief,
    @SerialName("participants_count") val participantsCount: Int = 0,
    @SerialName("free_slots") val freeSlots: Int = 0,
    val joined: Boolean = false,
    @SerialName("is_organizer") val isOrganizer: Boolean = false,
    val participants: List<Participant> = emptyList(),
)

@Serializable data class GamesResponse(val items: List<Game>)

@Serializable
data class GameBody(
    @SerialName("venue_id") val venueId: Long,
    val title: String,
    @SerialName("starts_at") val startsAt: String,
    @SerialName("max_players") val maxPlayers: Int,
)

@Serializable data class InviteBody(@SerialName("user_ids") val userIds: List<Long>)
@Serializable data class InviteResult(val sent: List<Long> = emptyList(), val skipped: List<Long> = emptyList())

// ---------------------------------------------------------------- сообщения и уведомления
@Serializable
data class Message(
    val id: Long,
    @SerialName("sender_id") val senderId: Long,
    @SerialName("recipient_id") val recipientId: Long,
    val body: String,
    @SerialName("created_at") val createdAt: String,
    @SerialName("read_at") val readAt: String? = null,
    val mine: Boolean = false,
)

@Serializable data class MessagesResponse(val items: List<Message>, @SerialName("has_more") val hasMore: Boolean = false)
@Serializable data class MessageBody(val body: String)

@Serializable
data class LastMessage(val id: Long, val body: String, @SerialName("created_at") val createdAt: String, val mine: Boolean = false)

@Serializable
data class Conversation(
    val user: UserBrief,
    @SerialName("is_friend") val isFriend: Boolean = false,
    val online: Boolean? = null,
    val unread: Int = 0,
    @SerialName("last_message") val lastMessage: LastMessage,
)

@Serializable data class ConversationsResponse(val items: List<Conversation>)

@Serializable
data class NotificationItem(
    val id: Long,
    val type: String,
    val title: String,
    val body: String? = null,
    @SerialName("ref_id") val refId: Long? = null,
    @SerialName("created_at") val createdAt: String,
    @SerialName("read_at") val readAt: String? = null,
)

@Serializable
data class NotificationsResponse(val items: List<NotificationItem>, @SerialName("unread_count") val unreadCount: Int = 0)

@Serializable
data class UnreadCounts(
    @SerialName("unread_count") val unreadCount: Int = 0,
    @SerialName("unread_messages") val unreadMessages: Int = 0,
)

// ---------------------------------------------------------------- блокировки, жалобы, роли, админка
@Serializable data class BlockItem(val user: UserBrief, @SerialName("created_at") val createdAt: String = "")
@Serializable data class BlocksResponse(val items: List<BlockItem>)

@Serializable
data class ReportBody(
    @SerialName("target_user_id") val targetUserId: Long? = null,
    @SerialName("target_venue_id") val targetVenueId: Long? = null,
    @SerialName("target_game_id") val targetGameId: Long? = null,
    val reason: String,
    val description: String? = null,
)

@Serializable data class ModeratorRequestBody(val message: String? = null)

@Serializable
data class ModeratorRequest(
    val id: Long,
    val message: String? = null,
    val status: String,
    @SerialName("decision_reason") val decisionReason: String? = null,
    @SerialName("created_at") val createdAt: String,
    @SerialName("decided_at") val decidedAt: String? = null,
    val user: UserBrief? = null,
)

@Serializable data class ModeratorRequestsResponse(val items: List<ModeratorRequest>)

@Serializable
data class AdminUser(
    val id: Long,
    val login: String,
    @SerialName("display_name") val displayName: String,
    @SerialName("avatar_url") val avatarUrl: String? = null,
    val role: String,
    @SerialName("is_active") val isActive: Boolean = true,
    @SerialName("can_review_reports") val canReviewReports: Boolean = false,
    @SerialName("must_change_password") val mustChangePassword: Boolean = false,
    @SerialName("created_at") val createdAt: String = "",
    @SerialName("last_seen_at") val lastSeenAt: String? = null,
)

@Serializable data class AdminUsersResponse(val items: List<AdminUser>)
@Serializable data class RoleBody(val role: String)
@Serializable data class ActiveBody(@SerialName("is_active") val isActive: Boolean)
@Serializable data class ReviewFlagBody(@SerialName("can_review_reports") val canReviewReports: Boolean)
@Serializable data class ArchiveBody(val archived: Boolean)
@Serializable data class TempPassword(val id: Long, val login: String, @SerialName("temporary_password") val temporaryPassword: String)

@Serializable
data class AdminReport(
    val id: Long,
    val reason: String,
    val description: String? = null,
    val status: String,
    @SerialName("created_at") val createdAt: String,
    val reporter: UserBrief,
    @SerialName("target_user") val targetUser: UserBrief? = null,
    @SerialName("target_venue_id") val targetVenueId: Long? = null,
    @SerialName("target_venue_name") val targetVenueName: String? = null,
    @SerialName("target_game_id") val targetGameId: Long? = null,
    @SerialName("target_game_title") val targetGameTitle: String? = null,
)

@Serializable data class AdminReportsResponse(val items: List<AdminReport>)
@Serializable data class ResolveBody(val status: String, val note: String? = null)
@Serializable data class SportBody(val name: String)
@Serializable data class SportPatchBody(val name: String? = null, @SerialName("is_active") val isActive: Boolean? = null)

@Serializable
data class AuditEntry(
    val id: Long,
    val action: String,
    @SerialName("target_type") val targetType: String? = null,
    @SerialName("target_id") val targetId: Long? = null,
    val details: String? = null,
    @SerialName("created_at") val createdAt: String,
    @SerialName("actor_login") val actorLogin: String? = null,
)

@Serializable data class AuditResponse(val items: List<AuditEntry>)

@Serializable data class DiskInfo(@SerialName("free_gb") val freeGb: Double = 0.0, @SerialName("total_gb") val totalGb: Double = 0.0)

@Serializable
data class SystemCounts(
    val users: Int = 0,
    val venues: Int = 0,
    @SerialName("pending_submissions") val pendingSubmissions: Int = 0,
    @SerialName("pending_proposals") val pendingProposals: Int = 0,
    @SerialName("open_reports") val openReports: Int = 0,
    @SerialName("pending_moderator_requests") val pendingModeratorRequests: Int = 0,
)

@Serializable
data class SystemStatus(val disk: DiskInfo = DiskInfo(), val warnings: List<String> = emptyList(), val counts: SystemCounts = SystemCounts())

// ---------------------------------------------------------------- служебные
@Serializable data class RegisterBody(val login: String, val password: String)
@Serializable data class LoginBody(val login: String, val password: String)
@Serializable data class ChangePasswordBody(@SerialName("current_password") val currentPassword: String, @SerialName("new_password") val newPassword: String)
@Serializable data class ChangeLoginBody(val password: String, @SerialName("new_login") val newLogin: String)
@Serializable data class DeleteAccountBody(val password: String)
@Serializable data class ProfileBody(@SerialName("display_name") val displayName: String? = null, @SerialName("favorite_sport_ids") val favoriteSportIds: List<Int>? = null)
@Serializable data class HealthResponse(val status: String = "", val service: String = "", val version: String = "")

@Serializable data class ErrorEnvelope(val error: ErrorBody? = null)
@Serializable data class ErrorBody(val code: String = "", val message: String = "", val details: kotlinx.serialization.json.JsonElement? = null)