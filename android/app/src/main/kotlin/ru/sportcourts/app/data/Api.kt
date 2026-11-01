package ru.sportcourts.app.data

import okhttp3.MultipartBody
import retrofit2.http.Body
import retrofit2.http.DELETE
import retrofit2.http.GET
import retrofit2.http.HTTP
import retrofit2.http.Multipart
import retrofit2.http.PATCH
import retrofit2.http.POST
import retrofit2.http.PUT
import retrofit2.http.Part
import retrofit2.http.Path
import retrofit2.http.Query

/** Все эндпоинты сервера (префикс /api/v1 задаётся в базовом адресе). */
interface Api {
    // ---- авторизация
    @POST("auth/register") suspend fun register(@Body body: RegisterBody): AuthResponse
    @POST("auth/login") suspend fun login(@Body body: LoginBody): AuthResponse
    @POST("auth/logout") suspend fun logout()
    @GET("auth/me") suspend fun me(): Me
    @POST("auth/change-password") suspend fun changePassword(@Body body: ChangePasswordBody): Me
    @POST("auth/change-login") suspend fun changeLogin(@Body body: ChangeLoginBody): Me

    // ---- профиль
    @GET("sports") suspend fun sports(): SportsResponse
    @PATCH("me") suspend fun updateProfile(@Body body: ProfileBody): Me
    @Multipart @PUT("me/avatar") suspend fun setAvatar(@Part file: MultipartBody.Part): Me
    @DELETE("me/avatar") suspend fun deleteAvatar(): Me
    @POST("me/heartbeat") suspend fun heartbeat()
    @HTTP(method = "DELETE", path = "me", hasBody = true) suspend fun deleteAccount(@Body body: DeleteAccountBody)
    @GET("users/search") suspend fun searchUsers(@Query("q") q: String): UsersResponse
    @GET("users/{id}") suspend fun user(@Path("id") id: Long): UserProfile

    // ---- площадки
    @GET("venues") suspend fun venues(
        @Query("q") q: String? = null,
        @Query("sport_id") sportId: Int? = null,
        @Query("venue_type") venueType: String? = null,
        @Query("min_players") minPlayers: Int? = null,
        @Query("lat") lat: Double? = null,
        @Query("lon") lon: Double? = null,
        @Query("radius_km") radiusKm: Double? = null,
        @Query("sort") sort: String? = null,
        @Query("limit") limit: Int = 200,
    ): VenuesResponse

    @GET("venues/{id}") suspend fun venue(
        @Path("id") id: Long,
        @Query("lat") lat: Double? = null,
        @Query("lon") lon: Double? = null,
    ): Venue

    @POST("venues/{id}/presence/toggle") suspend fun togglePresence(@Path("id") id: Long): PresenceResult
    @POST("venues/{id}/player-reports") suspend fun reportPlayers(@Path("id") id: Long, @Body body: PlayerReportBody): PlayerReportResult
    @GET("venues/{id}/player-reports") suspend fun playerReports(@Path("id") id: Long, @Query("limit") limit: Int = 20): PlayerReportsResponse
    @POST("venues/check-duplicates") suspend fun checkDuplicates(@Body body: VenueBody): DuplicatesResponse
    @Multipart @POST("uploads/venue-photo") suspend fun uploadVenuePhoto(@Part file: MultipartBody.Part): UploadResult

    // ---- заявки и предложения
    @POST("venue-submissions") suspend fun submitVenue(@Body body: VenueBody): CreatedResult
    @GET("venue-submissions/mine") suspend fun mySubmissions(): SubmissionsResponse
    @POST("venues/{id}/proposals") suspend fun proposeChange(@Path("id") id: Long, @Body body: VenueBody): CreatedResult
    @GET("venue-change-proposals/mine") suspend fun myProposals(): ProposalsResponse

    // ---- модерация
    @GET("moderation/submissions") suspend fun modSubmissions(@Query("status") status: String = "pending"): SubmissionsResponse
    @POST("moderation/submissions/{id}/approve") suspend fun approveSubmission(@Path("id") id: Long): CreatedResult
    @POST("moderation/submissions/{id}/reject") suspend fun rejectSubmission(@Path("id") id: Long, @Body body: RejectBody): CreatedResult
    @GET("moderation/proposals") suspend fun modProposals(@Query("status") status: String = "pending"): ProposalsResponse
    @POST("moderation/proposals/{id}/approve") suspend fun approveProposal(@Path("id") id: Long): CreatedResult
    @POST("moderation/proposals/{id}/reject") suspend fun rejectProposal(@Path("id") id: Long, @Body body: RejectBody): CreatedResult
    @GET("moderation/decisions") suspend fun decisions(@Query("limit") limit: Int = 50): DecisionsResponse

    // ---- игры
    @GET("games") suspend fun games(
        @Query("scope") scope: String = "open",
        @Query("venue_id") venueId: Long? = null,
    ): GamesResponse

    @POST("games") suspend fun createGame(@Body body: GameBody): Game
    @GET("games/{id}") suspend fun game(@Path("id") id: Long): Game
    @POST("games/{id}/join") suspend fun joinGame(@Path("id") id: Long): Game
    @POST("games/{id}/leave") suspend fun leaveGame(@Path("id") id: Long): Game
    @POST("games/{id}/cancel") suspend fun cancelGame(@Path("id") id: Long): Game
    @POST("games/{id}/finish") suspend fun finishGame(@Path("id") id: Long): Game
    @POST("games/{id}/invite") suspend fun inviteToGame(@Path("id") id: Long, @Body body: InviteBody): InviteResult

    // ---- друзья
    @GET("friends") suspend fun friends(): FriendsResponse
    @DELETE("friends/{id}") suspend fun removeFriend(@Path("id") id: Long)
    @GET("friend-requests") suspend fun friendRequests(@Query("direction") direction: String = "incoming"): FriendRequestsResponse
    @POST("friend-requests") suspend fun sendFriendRequest(@Body body: Map<String, Long>): FriendRequestResult
    @POST("friend-requests/{id}/accept") suspend fun acceptRequest(@Path("id") id: Long): CreatedResult
    @POST("friend-requests/{id}/decline") suspend fun declineRequest(@Path("id") id: Long): CreatedResult
    @DELETE("friend-requests/{id}") suspend fun cancelRequest(@Path("id") id: Long)

    // ---- блокировки и жалобы
    @GET("blocks") suspend fun blocks(): BlocksResponse
    @POST("blocks/{id}") suspend fun block(@Path("id") id: Long)
    @DELETE("blocks/{id}") suspend fun unblock(@Path("id") id: Long)
    @POST("reports") suspend fun report(@Body body: ReportBody): CreatedResult

    // ---- сообщения
    @GET("conversations") suspend fun conversations(): ConversationsResponse
    @GET("messages/{id}") suspend fun messages(
        @Path("id") id: Long,
        @Query("before_id") beforeId: Long? = null,
        @Query("after_id") afterId: Long? = null,
        @Query("limit") limit: Int = 30,
    ): MessagesResponse

    @POST("messages/{id}") suspend fun sendMessage(@Path("id") id: Long, @Body body: MessageBody): Message
    @POST("messages/{id}/read") suspend fun markRead(@Path("id") id: Long)

    // ---- уведомления
    @GET("notifications") suspend fun notifications(@Query("limit") limit: Int = 50): NotificationsResponse
    @GET("notifications/unread-count") suspend fun unreadCount(): UnreadCounts
    @POST("notifications/read-all") suspend fun readAllNotifications()
    @POST("notifications/{id}/read") suspend fun readNotification(@Path("id") id: Long)

    // ---- роль модератора
    @POST("moderator-requests") suspend fun requestModerator(@Body body: ModeratorRequestBody): CreatedResult
    @GET("moderator-requests/mine") suspend fun myModeratorRequests(): ModeratorRequestsResponse

    // ---- администрирование
    @GET("admin/users") suspend fun adminUsers(@Query("q") q: String? = null): AdminUsersResponse
    @PUT("admin/users/{id}/role") suspend fun setRole(@Path("id") id: Long, @Body body: RoleBody): CreatedResult
    @PUT("admin/users/{id}/active") suspend fun setActive(@Path("id") id: Long, @Body body: ActiveBody): CreatedResult
    @PUT("admin/users/{id}/review-reports") suspend fun setReviewFlag(@Path("id") id: Long, @Body body: ReviewFlagBody): CreatedResult
    @POST("admin/users/{id}/reset-password") suspend fun resetPassword(@Path("id") id: Long): TempPassword
    @GET("admin/moderator-requests") suspend fun adminModeratorRequests(@Query("status") status: String = "pending"): ModeratorRequestsResponse
    @POST("admin/moderator-requests/{id}/approve") suspend fun approveModerator(@Path("id") id: Long): CreatedResult
    @POST("admin/moderator-requests/{id}/reject") suspend fun rejectModerator(@Path("id") id: Long, @Body body: RejectBody): CreatedResult
    @GET("admin/reports") suspend fun adminReports(@Query("status") status: String = "open"): AdminReportsResponse
    @POST("admin/reports/{id}/resolve") suspend fun resolveReport(@Path("id") id: Long, @Body body: ResolveBody): CreatedResult
    @POST("admin/venues") suspend fun adminCreateVenue(@Body body: VenueBody): Venue
    @PUT("admin/venues/{id}") suspend fun adminUpdateVenue(@Path("id") id: Long, @Body body: VenueBody): Venue
    @PUT("admin/venues/{id}/archive") suspend fun adminArchiveVenue(@Path("id") id: Long, @Body body: ArchiveBody): CreatedResult
    @GET("admin/sports") suspend fun adminSports(): SportsResponse
    @POST("admin/sports") suspend fun adminAddSport(@Body body: SportBody): Sport
    @PATCH("admin/sports/{id}") suspend fun adminPatchSport(@Path("id") id: Long, @Body body: SportPatchBody): SportsResponse
    @GET("admin/audit") suspend fun audit(@Query("limit") limit: Int = 50): AuditResponse
    @GET("admin/system") suspend fun system(): SystemStatus
}