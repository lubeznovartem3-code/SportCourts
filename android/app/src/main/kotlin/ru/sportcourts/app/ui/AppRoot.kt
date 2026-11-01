package ru.sportcourts.app.ui

import androidx.activity.compose.BackHandler
import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.animation.slideInHorizontally
import androidx.compose.animation.slideOutHorizontally
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.unit.dp
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.compose.LocalLifecycleOwner
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.lifecycle.repeatOnLifecycle
import androidx.navigation.NavType
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.compose.rememberNavController
import androidx.navigation.navArgument
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import ru.sportcourts.app.core.ApiResult
import ru.sportcourts.app.core.AppContainer
import ru.sportcourts.app.core.Session
import ru.sportcourts.app.data.Me
import ru.sportcourts.app.ui.components.Avatar
import ru.sportcourts.app.ui.components.Badge
import ru.sportcourts.app.ui.components.Divider
import ru.sportcourts.app.ui.screens.AdminScreen
import ru.sportcourts.app.ui.screens.AddFriendScreen
import ru.sportcourts.app.ui.screens.AuthScreen
import ru.sportcourts.app.ui.screens.BlocksScreen
import ru.sportcourts.app.ui.screens.ChatScreen
import ru.sportcourts.app.ui.screens.ConversationsScreen
import ru.sportcourts.app.ui.screens.CreateGameScreen
import ru.sportcourts.app.ui.screens.ForcePasswordScreen
import ru.sportcourts.app.ui.screens.FriendsScreen
import ru.sportcourts.app.ui.screens.GameScreen
import ru.sportcourts.app.ui.screens.GamesScreen
import ru.sportcourts.app.ui.screens.MapScreen
import ru.sportcourts.app.ui.screens.MySubmissionsScreen
import ru.sportcourts.app.ui.screens.ModerationScreen
import ru.sportcourts.app.ui.screens.NotificationsScreen
import ru.sportcourts.app.ui.screens.ProfileScreen
import ru.sportcourts.app.ui.screens.SettingsScreen
import ru.sportcourts.app.ui.screens.UnreachableScreen
import ru.sportcourts.app.ui.screens.UserProfileScreen
import ru.sportcourts.app.ui.screens.VenueFormScreen
import ru.sportcourts.app.ui.theme.AppType
import ru.sportcourts.app.ui.theme.SportCourtsTheme
import ru.sportcourts.app.ui.theme.colors

@Composable
fun AppRoot(container: AppContainer, mapKitReady: Boolean) {
    val settings by container.settings.collectAsStateWithLifecycle()
    val session by container.session.collectAsStateWithLifecycle()
    val toaster = remember { Toaster() }
    LaunchedEffect(Unit) { container.start() }

    val systemDark = isSystemInDarkTheme()
    val dark = when (settings?.theme) {
        "dark" -> true
        "light" -> false
        else -> systemDark
    }

    CompositionLocalProvider(LocalContainer provides container, LocalToaster provides toaster, LocalMapKitReady provides mapKitReady) {
        SportCourtsTheme(dark) {
            Box(Modifier.fillMaxSize()) {
                if (settings != null) {
                    when (val s = session) {
                        is Session.Loading -> Unit
                        is Session.LoggedOut -> AuthScreen()
                        is Session.Unreachable -> UnreachableScreen(s.message)
                        is Session.In -> if (s.me.mustChangePassword) ForcePasswordScreen() else MainShell(s.me)
                    }
                }
                ToastHost(toaster)
            }
        }
    }
}

@Composable
private fun ToastHost(toaster: Toaster) {
    val msg = toaster.message
    LaunchedEffect(msg) {
        if (msg != null) {
            delay(3500)
            if (toaster.message == msg) toaster.message = null
        }
    }
    if (msg != null) {
        Box(Modifier.fillMaxSize().navigationBarsPadding().padding(bottom = 24.dp, start = 24.dp, end = 24.dp), contentAlignment = Alignment.BottomCenter) {
            Box(
                Modifier.clip(RoundedCornerShape(12.dp)).background(colors.primary).clickable { toaster.message = null }
                    .padding(horizontal = 16.dp, vertical = 12.dp)
            ) { Text(msg, style = AppType.small, color = colors.onPrimary) }
        }
    }
}

private data class DrawerItem(val route: String, val title: String, val badge: Int = 0)

@Composable
private fun MainShell(me: Me) {
    val container = LocalContainer.current
    val nav = rememberNavController()
    var drawerOpen by remember { mutableStateOf(false) }
    val unread by container.unread.collectAsStateWithLifecycle()
    val scope = androidx.compose.runtime.rememberCoroutineScope()
    val lifecycleOwner = LocalLifecycleOwner.current

    // Пока приложение на экране: раз в минуту отмечаем присутствие (статус «в сети»), раз в 30 секунд обновляем счётчики.
    LaunchedEffect(me.id) {
        lifecycleOwner.lifecycle.repeatOnLifecycle(Lifecycle.State.STARTED) {
            launch {
                while (true) {
                    container.repo.call { it.heartbeat() }
                    delay(60_000)
                }
            }
            launch {
                while (true) {
                    val r = container.repo.call { it.unreadCount() }
                    if (r is ApiResult.Ok) container.updateUnread(r.value)
                    delay(30_000)
                }
            }
        }
    }

    fun navigateTop(route: String) {
        drawerOpen = false
        nav.navigate(route) {
            popUpTo("map") { inclusive = false }
            launchSingleTop = true
        }
    }

    val shell = remember(nav) {
        ShellActions(
            openDrawer = { drawerOpen = true },
            navigate = { route ->
                if (route in topRoutes) navigateTop(route)
                else nav.navigate(route) { launchSingleTop = true }
            },
            back = { nav.popBackStack() },
        )
    }

    BackHandler(enabled = drawerOpen) { drawerOpen = false }

    CompositionLocalProvider(LocalShell provides shell) {
        Box(Modifier.fillMaxSize()) {
            NavHost(navController = nav, startDestination = "map", modifier = Modifier.fillMaxSize()) {
                composable("map") { MapScreen() }
                composable("games") { GamesScreen() }
                composable("game/new/{venueId}", listOf(navArgument("venueId") { type = NavType.LongType })) {
                    CreateGameScreen(it.arguments?.getLong("venueId") ?: 0L)
                }
                composable("game/{id}", listOf(navArgument("id") { type = NavType.LongType })) {
                    GameScreen(it.arguments?.getLong("id") ?: 0L)
                }
                composable("chats") { ConversationsScreen() }
                composable("chat/{id}", listOf(navArgument("id") { type = NavType.LongType })) {
                    ChatScreen(it.arguments?.getLong("id") ?: 0L)
                }
                composable("friends") { FriendsScreen() }
                composable("friends/add") { AddFriendScreen() }
                composable("user/{id}", listOf(navArgument("id") { type = NavType.LongType })) {
                    UserProfileScreen(it.arguments?.getLong("id") ?: 0L)
                }
                composable("profile") { ProfileScreen() }
                composable("settings") { SettingsScreen() }
                composable("settings/blocks") { BlocksScreen() }
                composable("notifications") { NotificationsScreen() }
                composable("venue/new") { VenueFormScreen(editVenueId = null) }
                composable("venue/edit/{id}", listOf(navArgument("id") { type = NavType.LongType })) {
                    VenueFormScreen(editVenueId = it.arguments?.getLong("id"))
                }
                composable("submissions") { MySubmissionsScreen() }
                composable("moderation") { ModerationScreen() }
                composable("admin") { AdminScreen() }
            }

            AnimatedVisibility(visible = drawerOpen, enter = fadeIn(), exit = fadeOut()) {
                Box(Modifier.fillMaxSize().background(colors.scrim).clickable { drawerOpen = false })
            }
            AnimatedVisibility(
                visible = drawerOpen,
                enter = slideInHorizontally { -it },
                exit = slideOutHorizontally { -it },
            ) {
                DrawerPanel(me, unread.unreadCount, unread.unreadMessages, onNavigate = { navigateTop(it) })
            }
        }
    }
}

private val topRoutes = setOf(
    "map", "games", "chats", "friends", "profile", "settings", "notifications", "submissions", "moderation", "admin",
)

@Composable
private fun DrawerPanel(me: Me, unreadNotifications: Int, unreadMessages: Int, onNavigate: (String) -> Unit) {
    val c = colors
    val items = buildList {
        add(DrawerItem("map", "Карта площадок"))
        add(DrawerItem("games", "Игры"))
        add(DrawerItem("chats", "Сообщения", unreadMessages))
        add(DrawerItem("friends", "Друзья"))
        add(DrawerItem("notifications", "Уведомления", unreadNotifications))
        add(DrawerItem("profile", "Профиль"))
        add(DrawerItem("submissions", "Мои заявки"))
        if (me.isModerator) add(DrawerItem("moderation", "Модерация"))
        if (me.isAdmin) add(DrawerItem("admin", "Администрирование"))
    }
    Column(
        Modifier.fillMaxHeight().width(300.dp).background(c.background).statusBarsPadding().navigationBarsPadding(),
    ) {
        val container = LocalContainer.current
        Row(
            Modifier.fillMaxWidth().clickable { onNavigate("profile") }.padding(20.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Avatar(container.repo.mediaUrl(me.avatarUrl), me.displayName, size = 48.dp)
            Spacer(Modifier.width(14.dp))
            Column {
                Text(me.displayName, style = AppType.bodyBold, color = c.text, maxLines = 1)
                Text("@" + me.login, style = AppType.caption, color = c.textSecondary, maxLines = 1)
            }
        }
        Divider()
        Column(Modifier.weight(1f).verticalScroll(rememberScrollState()).padding(horizontal = 10.dp, vertical = 10.dp), verticalArrangement = Arrangement.spacedBy(2.dp)) {
            items.forEach { item -> DrawerRow(item.title, item.badge) { onNavigate(item.route) } }
        }
        Divider()
        Column(Modifier.padding(horizontal = 10.dp, vertical = 10.dp)) {
            DrawerRow("Настройки", 0) { onNavigate("settings") }
        }
        Spacer(Modifier.height(4.dp))
    }
}

@Composable
private fun DrawerRow(title: String, badge: Int, onClick: () -> Unit) {
    Row(
        Modifier.fillMaxWidth().clip(RoundedCornerShape(10.dp)).clickable(onClick = onClick).padding(horizontal = 14.dp, vertical = 14.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Text(title, style = AppType.body, color = colors.text, modifier = Modifier.weight(1f))
        Badge(badge)
    }
}
