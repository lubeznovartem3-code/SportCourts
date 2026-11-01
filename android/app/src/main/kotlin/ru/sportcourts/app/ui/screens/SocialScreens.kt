package ru.sportcourts.app.ui.screens

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.Send
import androidx.compose.material.icons.filled.Add
import androidx.compose.material.icons.filled.Email
import androidx.compose.material.icons.filled.MoreVert
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.compose.LocalLifecycleOwner
import androidx.lifecycle.repeatOnLifecycle
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import ru.sportcourts.app.core.ApiError
import ru.sportcourts.app.core.ApiResult
import ru.sportcourts.app.data.InviteBody
import ru.sportcourts.app.data.Message
import ru.sportcourts.app.data.MessageBody
import ru.sportcourts.app.data.UserBrief
import ru.sportcourts.app.ui.Load
import ru.sportcourts.app.ui.LoadView
import ru.sportcourts.app.ui.LocalContainer
import ru.sportcourts.app.ui.LocalShell
import ru.sportcourts.app.ui.LocalToaster
import ru.sportcourts.app.ui.components.AppCard
import ru.sportcourts.app.ui.components.AppTextField
import ru.sportcourts.app.ui.components.Avatar
import ru.sportcourts.app.ui.components.Badge
import ru.sportcourts.app.ui.components.ConfirmDialog
import ru.sportcourts.app.ui.components.Divider
import ru.sportcourts.app.ui.components.EmptyState
import ru.sportcourts.app.ui.components.ErrorState
import ru.sportcourts.app.ui.components.FormColumn
import ru.sportcourts.app.ui.components.IconAction
import ru.sportcourts.app.ui.components.InlineError
import ru.sportcourts.app.ui.components.LoadingBox
import ru.sportcourts.app.ui.components.PickerDialog
import ru.sportcourts.app.ui.components.PrimaryButton
import ru.sportcourts.app.ui.components.ReportDialog
import ru.sportcourts.app.ui.components.Screen
import ru.sportcourts.app.ui.components.SecondaryButton
import ru.sportcourts.app.ui.components.SectionHeader
import ru.sportcourts.app.ui.components.TabBar
import ru.sportcourts.app.ui.components.Tag
import ru.sportcourts.app.ui.components.ChipFlow
import ru.sportcourts.app.ui.formatAgo
import ru.sportcourts.app.ui.formatClock
import ru.sportcourts.app.ui.formatGameTime
import ru.sportcourts.app.ui.rememberLoader
import ru.sportcourts.app.ui.theme.AppType
import ru.sportcourts.app.ui.theme.colors

private fun UserBrief.title() = displayName.ifEmpty { login }

/** Периодическое «тихое» обновление данных экрана, пока он на экране. */
@Composable
private fun <T> AutoRefresh(loader: ru.sportcourts.app.ui.Loader<T>, everyMs: Long) {
    val owner = LocalLifecycleOwner.current
    LaunchedEffect(loader) {
        owner.lifecycle.repeatOnLifecycle(Lifecycle.State.STARTED) {
            while (true) {
                delay(everyMs)
                loader.load(silent = true)
            }
        }
    }
}

// ------------------------------------------------------------------ друзья
@Composable
fun FriendsScreen() {
    val container = LocalContainer.current
    val shell = LocalShell.current
    val toaster = LocalToaster.current
    val scope = rememberCoroutineScope()
    var filter by remember { mutableStateOf("") }
    val friends = rememberLoader { container.repo.call { it.friends() } }
    val requests = rememberLoader { container.repo.call { it.friendRequests("incoming") } }
    AutoRefresh(friends, 30_000)
    AutoRefresh(requests, 30_000)

    Screen("Друзья", onMenu = { shell.openDrawer() }, actions = {
        IconAction(Icons.Filled.Add, "Найти друзей", { shell.navigate("friends/add") })
    }) {
        LoadView(friends, Modifier.fillMaxSize()) { resp ->
            val incoming = (requests.value?.items).orEmpty()
            if (resp.items.isEmpty() && incoming.isEmpty()) {
                EmptyState(
                    "Список друзей пуст", "Здесь будут отображаться ваши друзья, когда появятся в сети или добавят вас.",
                    mark = "☺", action = "Найти друзей", onAction = { shell.navigate("friends/add") },
                )
            } else {
                val q = filter.trim().lowercase()
                val shown = resp.items.filter { q.isEmpty() || it.displayName.lowercase().contains(q) || it.login.lowercase().contains(q) }
                LazyColumn(Modifier.fillMaxSize(), contentPadding = PaddingValues(horizontal = 16.dp, vertical = 12.dp)) {
                    if (incoming.isNotEmpty()) {
                        item {
                            SectionHeader("Запросы в друзья")
                            Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                                incoming.forEach { r ->
                                    RequestRow(r.user, onAccept = {
                                        scope.launch {
                                            val res = container.repo.call { it.acceptRequest(r.id) }
                                            if (res is ApiResult.Fail) toaster.show(res.error.message)
                                            requests.load(silent = true); friends.load(silent = true)
                                        }
                                    }, onDecline = {
                                        scope.launch {
                                            val res = container.repo.call { it.declineRequest(r.id) }
                                            if (res is ApiResult.Fail) toaster.show(res.error.message)
                                            requests.load(silent = true)
                                        }
                                    })
                                }
                            }
                        }
                    }
                    item {
                        Spacer(Modifier.padding(top = 12.dp))
                        AppTextField(filter, { filter = it }, placeholder = "Поиск друзей…", maxLength = 50)
                    }
                    val online = shown.filter { it.online }
                    val offline = shown.filter { !it.online }
                    if (online.isNotEmpty()) {
                        item { SectionHeader("В сети") }
                        items(online, key = { "o" + it.id }) { f -> FriendRow(f) { shell.navigate(it) } }
                    }
                    if (offline.isNotEmpty()) {
                        item { SectionHeader("Не в сети") }
                        items(offline, key = { "f" + it.id }) { f -> FriendRow(f) { shell.navigate(it) } }
                    }
                    if (shown.isEmpty() && resp.items.isNotEmpty()) {
                        item { Text("Никого не найдено", style = AppType.small, color = colors.textSecondary, modifier = Modifier.padding(top = 24.dp)) }
                    }
                }
            }
        }
    }
}

@Composable
private fun FriendRow(f: ru.sportcourts.app.data.Friend, navigate: (String) -> Unit) {
    val container = LocalContainer.current
    val name = f.displayName.ifEmpty { f.login }
    Row(
        Modifier.fillMaxWidth().clickable { navigate("user/${f.id}") }.padding(vertical = 8.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Avatar(container.repo.mediaUrl(f.avatarUrl), name, 44.dp, online = f.online)
        Spacer(Modifier.width(12.dp))
        Column(Modifier.weight(1f)) {
            Text(name, style = AppType.bodyBold, color = colors.text, maxLines = 1, overflow = TextOverflow.Ellipsis)
            val sub = if (f.online) (f.activity ?: "В сети") else if (f.lastSeenAt != null) "Был(а) в сети ${formatAgo(f.lastSeenAt)}" else "Не в сети"
            Text(sub, style = AppType.caption, color = if (f.online && f.activity == null) colors.online else colors.textSecondary, maxLines = 1, overflow = TextOverflow.Ellipsis)
        }
        Box {
            IconAction(Icons.Filled.Email, "Написать", { navigate("chat/${f.id}") }, tint = colors.textSecondary)
            if (f.unreadMessages > 0) Badge(f.unreadMessages, Modifier.align(Alignment.TopEnd))
        }
    }
}

@Composable
private fun RequestRow(user: UserBrief, onAccept: () -> Unit, onDecline: () -> Unit) {
    val container = LocalContainer.current
    val shell = LocalShell.current
    AppCard {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Avatar(container.repo.mediaUrl(user.avatarUrl), user.title(), 40.dp)
            Spacer(Modifier.width(12.dp))
            Column(Modifier.weight(1f).clickable { shell.navigate("user/${user.id}") }) {
                Text(user.title(), style = AppType.bodyBold, color = colors.text, maxLines = 1, overflow = TextOverflow.Ellipsis)
                Text("@" + user.login, style = AppType.caption, color = colors.textSecondary)
            }
            Column(horizontalAlignment = Alignment.End, verticalArrangement = Arrangement.spacedBy(6.dp)) {
                Box(Modifier.widthIn(min = 96.dp)) { PrimaryButton("Принять", onAccept, Modifier.heightIn(max = 38.dp)) }
                Box(Modifier.widthIn(min = 96.dp)) { SecondaryButton("Отклонить", onDecline) }
            }
        }
    }
}

// ------------------------------------------------------------------ поиск людей и заявки
@Composable
fun AddFriendScreen() {
    val container = LocalContainer.current
    val shell = LocalShell.current
    val toaster = LocalToaster.current
    val scope = rememberCoroutineScope()
    var tab by remember { mutableStateOf(0) }
    var query by remember { mutableStateOf("") }
    var results by remember { mutableStateOf<Load<List<UserBrief>>?>(null) }
    val incoming = rememberLoader { container.repo.call { it.friendRequests("incoming") } }
    val outgoing = rememberLoader { container.repo.call { it.friendRequests("outgoing") } }

    LaunchedEffect(query) {
        val q = query.trim()
        if (q.length < 2) { results = null; return@LaunchedEffect }
        delay(350)
        results = Load.Loading
        results = when (val r = container.repo.call { it.searchUsers(q) }) {
            is ApiResult.Ok -> Load.Ready(r.value.items)
            is ApiResult.Fail -> Load.Failed(r.error)
        }
    }

    fun send(u: UserBrief) {
        scope.launch {
            val r = container.repo.call { it.sendFriendRequest(mapOf("user_id" to u.id)) }
            when (r) {
                is ApiResult.Ok -> {
                    toaster.show(if (r.value.status == "accepted") "Вы теперь друзья" else "Запрос отправлен")
                    val q = query
                    query = ""; query = q   // повторный поиск, чтобы обновить кнопки
                    outgoing.load(silent = true); incoming.load(silent = true)
                }
                is ApiResult.Fail -> toaster.show(r.error.message)
            }
        }
    }

    Screen("Добавить друга", onBack = { shell.back() }) {
        Column(Modifier.fillMaxSize()) {
            TabBar(listOf("Поиск", "Входящие", "Исходящие"), tab, { tab = it }, badges = listOf(0, incoming.value?.items?.size ?: 0, 0))
            when (tab) {
                0 -> Column(Modifier.fillMaxSize().padding(16.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
                    AppTextField(query, { query = it }, placeholder = "Логин или имя (от 2 символов)", maxLength = 50, imeAction = ImeAction.Search)
                    when (val s = results) {
                        null -> Text("Введите логин или имя пользователя.", style = AppType.small, color = colors.textSecondary)
                        is Load.Loading -> LoadingBox()
                        is Load.Failed -> InlineError(s.error.message)
                        is Load.Ready -> if (s.value.isEmpty()) Text("Никого не найдено.", style = AppType.small, color = colors.textSecondary)
                        else LazyColumn(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                            items(s.value, key = { it.id }) { u ->
                                Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
                                    Avatar(container.repo.mediaUrl(u.avatarUrl), u.title(), 40.dp)
                                    Spacer(Modifier.width(12.dp))
                                    Column(Modifier.weight(1f).clickable { shell.navigate("user/${u.id}") }) {
                                        Text(u.title(), style = AppType.bodyBold, color = colors.text, maxLines = 1, overflow = TextOverflow.Ellipsis)
                                        Text("@" + u.login, style = AppType.caption, color = colors.textSecondary)
                                    }
                                    when (u.relation) {
                                        "friend" -> Tag("В друзьях")
                                        "request_sent" -> Tag("Запрос отправлен")
                                        "request_received" -> Tag("Ждёт ответа")
                                        else -> Box(Modifier.width(110.dp)) { SecondaryButton("Добавить", { send(u) }) }
                                    }
                                }
                            }
                        }
                    }
                }
                1 -> RequestList(incoming, incomingMode = true, onChanged = { incoming.load(silent = true) })
                else -> RequestList(outgoing, incomingMode = false, onChanged = { outgoing.load(silent = true) })
            }
        }
    }
}

@Composable
private fun RequestList(loader: ru.sportcourts.app.ui.Loader<ru.sportcourts.app.data.FriendRequestsResponse>, incomingMode: Boolean, onChanged: () -> Unit) {
    val container = LocalContainer.current
    val toaster = LocalToaster.current
    val scope = rememberCoroutineScope()
    LoadView(loader, Modifier.fillMaxSize()) { resp ->
        if (resp.items.isEmpty()) {
            EmptyState(if (incomingMode) "Входящих запросов нет" else "Исходящих запросов нет", if (incomingMode) "Когда кто-то захочет добавить вас в друзья, запрос появится здесь." else "Отправленные запросы, на которые ещё не ответили, будут здесь.")
        } else LazyColumn(Modifier.fillMaxSize(), contentPadding = PaddingValues(16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            items(resp.items, key = { it.id }) { r ->
                if (incomingMode) {
                    RequestRow(r.user, onAccept = {
                        scope.launch {
                            val res = container.repo.call { it.acceptRequest(r.id) }
                            if (res is ApiResult.Fail) toaster.show(res.error.message) else toaster.show("Вы теперь друзья")
                            onChanged()
                        }
                    }, onDecline = {
                        scope.launch {
                            val res = container.repo.call { it.declineRequest(r.id) }
                            if (res is ApiResult.Fail) toaster.show(res.error.message)
                            onChanged()
                        }
                    })
                } else {
                    AppCard {
                        Row(verticalAlignment = Alignment.CenterVertically) {
                            Avatar(container.repo.mediaUrl(r.user.avatarUrl), r.user.title(), 40.dp)
                            Spacer(Modifier.width(12.dp))
                            Column(Modifier.weight(1f)) {
                                Text(r.user.title(), style = AppType.bodyBold, color = colors.text, maxLines = 1)
                                Text("@" + r.user.login, style = AppType.caption, color = colors.textSecondary)
                            }
                            Box(Modifier.width(110.dp)) {
                                SecondaryButton("Отозвать", {
                                    scope.launch {
                                        val res = container.repo.call { it.cancelRequest(r.id) }
                                        if (res is ApiResult.Fail) toaster.show(res.error.message)
                                        onChanged()
                                    }
                                })
                            }
                        }
                    }
                }
            }
        }
    }
}

// ------------------------------------------------------------------ список переписок
@Composable
fun ConversationsScreen() {
    val container = LocalContainer.current
    val shell = LocalShell.current
    val loader = rememberLoader { container.repo.call { it.conversations() } }
    AutoRefresh(loader, 10_000)
    Screen("Сообщения", onMenu = { shell.openDrawer() }) {
        LoadView(loader, Modifier.fillMaxSize()) { resp ->
            if (resp.items.isEmpty()) {
                EmptyState("Сообщений пока нет", "Писать можно друзьям. Откройте раздел «Друзья» и начните переписку.",
                    action = "К друзьям", onAction = { shell.navigate("friends") })
            } else LazyColumn(Modifier.fillMaxSize(), contentPadding = PaddingValues(horizontal = 16.dp, vertical = 8.dp)) {
                items(resp.items, key = { it.user.id }) { c ->
                    Row(Modifier.fillMaxWidth().clickable { shell.navigate("chat/${c.user.id}") }.padding(vertical = 10.dp), verticalAlignment = Alignment.CenterVertically) {
                        Avatar(container.repo.mediaUrl(c.user.avatarUrl), c.user.title(), 46.dp, online = c.online)
                        Spacer(Modifier.width(12.dp))
                        Column(Modifier.weight(1f)) {
                            Row(verticalAlignment = Alignment.CenterVertically) {
                                Text(c.user.title(), style = AppType.bodyBold, color = colors.text, modifier = Modifier.weight(1f), maxLines = 1, overflow = TextOverflow.Ellipsis)
                                Text(formatClock(c.lastMessage.createdAt), style = AppType.caption, color = colors.textSecondary)
                            }
                            Text((if (c.lastMessage.mine) "Вы: " else "") + c.lastMessage.body, style = AppType.small,
                                color = if (c.unread > 0) colors.text else colors.textSecondary, maxLines = 1, overflow = TextOverflow.Ellipsis)
                        }
                        if (c.unread > 0) { Spacer(Modifier.width(8.dp)); Badge(c.unread) }
                    }
                    Divider()
                }
            }
        }
    }
}

// ------------------------------------------------------------------ чат
@Composable
fun ChatScreen(otherId: Long) {
    val container = LocalContainer.current
    val shell = LocalShell.current
    val toaster = LocalToaster.current
    val scope = rememberCoroutineScope()
    val owner = LocalLifecycleOwner.current
    val profile = rememberLoader(otherId) { container.repo.call { it.user(otherId) } }
    var messages by remember(otherId) { mutableStateOf<List<Message>>(emptyList()) }
    var hasMore by remember(otherId) { mutableStateOf(false) }
    var loaded by remember(otherId) { mutableStateOf(false) }
    var loadError by remember(otherId) { mutableStateOf<ApiError?>(null) }
    var text by remember(otherId) { mutableStateOf("") }
    var sendError by remember(otherId) { mutableStateOf<String?>(null) }
    var sending by remember(otherId) { mutableStateOf(false) }
    var menu by remember { mutableStateOf(false) }
    var confirmBlock by remember { mutableStateOf(false) }
    var showReport by remember { mutableStateOf(false) }
    var pickGame by remember { mutableStateOf(false) }
    val listState = rememberLazyListState()

    fun merge(incoming: List<Message>) {
        if (incoming.isEmpty()) return
        val known = messages.map { it.id }.toSet()
        val add = incoming.filter { it.id !in known }
        if (add.isNotEmpty()) messages = (messages + add).sortedBy { it.id }
    }

    // Сообщения: первая загрузка, затем опрос новых каждые ~3 секунды, пока чат открыт
    LaunchedEffect(otherId) {
        owner.lifecycle.repeatOnLifecycle(Lifecycle.State.STARTED) {
            while (true) {
                val last = messages.lastOrNull()?.id
                val r = container.repo.call { it.messages(otherId, afterId = last) }
                when (r) {
                    is ApiResult.Ok -> {
                        if (last == null) { messages = r.value.items; hasMore = r.value.hasMore } else merge(r.value.items)
                        loaded = true
                        loadError = null
                        if (r.value.items.any { !it.mine && it.readAt == null } || (last == null && r.value.items.isNotEmpty())) {
                            container.repo.call { it.markRead(otherId) }
                        }
                    }
                    is ApiResult.Fail -> { loadError = r.error; loaded = true }
                }
                delay(3000)
            }
        }
    }
    // новое сообщение внизу — прокрутить к нему
    LaunchedEffect(messages.lastOrNull()?.id) {
        if (messages.isNotEmpty()) listState.scrollToItem(0)
    }

    val p = profile.value
    Screen(
        title = p?.displayName ?: "Чат", onBack = { shell.back() },
        subtitle = when {
            p == null -> null
            p.online == true -> "В сети"
            p.lastSeenAt != null && p.isFriend -> "Был(а) в сети ${formatAgo(p.lastSeenAt)}"
            else -> null
        },
        subtitleColor = if (p?.online == true) colors.online else colors.textSecondary,
        leading = { if (p != null) Avatar(container.repo.mediaUrl(p.avatarUrl), p.displayName, 36.dp) },
        actions = {
            Box {
                IconAction(Icons.Filled.MoreVert, "Ещё", { menu = true })
                DropdownMenu(expanded = menu, onDismissRequest = { menu = false }) {
                    DropdownMenuItem(text = { Text("Профиль") }, onClick = { menu = false; shell.navigate("user/$otherId") })
                    DropdownMenuItem(text = { Text("Заблокировать") }, onClick = { menu = false; confirmBlock = true })
                    DropdownMenuItem(text = { Text("Пожаловаться") }, onClick = { menu = false; showReport = true })
                }
            }
        },
    ) {
        Column(Modifier.fillMaxSize()) {
            Box(Modifier.weight(1f).fillMaxWidth()) {
                when {
                    !loaded -> LoadingBox()
                    loadError != null && messages.isEmpty() -> ErrorState(loadError!!, onRetry = null)
                    messages.isEmpty() -> EmptyState("Сообщений пока нет", "Напишите первое сообщение.")
                    else -> LazyColumn(
                        Modifier.fillMaxSize(), state = listState, reverseLayout = true,
                        contentPadding = PaddingValues(horizontal = 14.dp, vertical = 10.dp), verticalArrangement = Arrangement.spacedBy(8.dp),
                    ) {
                        items(messages.asReversed(), key = { it.id }) { m -> Bubble(m) }
                        if (hasMore) {
                            item(key = "more") {
                                Box(Modifier.fillMaxWidth(), contentAlignment = Alignment.Center) {
                                    Text("Загрузить более ранние", style = AppType.small, color = colors.textSecondary,
                                        modifier = Modifier.clickable {
                                            val first = messages.firstOrNull()?.id ?: return@clickable
                                            scope.launch {
                                                val r = container.repo.call { it.messages(otherId, beforeId = first) }
                                                if (r is ApiResult.Ok) { merge(r.value.items); hasMore = r.value.hasMore }
                                                else if (r is ApiResult.Fail) toaster.show(r.error.message)
                                            }
                                        }.padding(12.dp))
                                }
                            }
                        }
                    }
                }
            }
            if (loadError != null && messages.isNotEmpty()) InlineError(loadError!!.message, Modifier.padding(horizontal = 16.dp, vertical = 4.dp))
            val canWrite = p == null || (p.isFriend && !p.blockedByMe)
            if (!canWrite) {
                Text(
                    if (p?.blockedByMe == true) "Вы заблокировали этого пользователя. Разблокировать можно в настройках." else "Писать можно только друзьям.",
                    style = AppType.small, color = colors.textSecondary, modifier = Modifier.fillMaxWidth().padding(16.dp),
                )
            } else {
                InlineError(sendError, Modifier.padding(horizontal = 16.dp, vertical = 4.dp))
                Divider()
                Row(Modifier.fillMaxWidth().padding(horizontal = 8.dp, vertical = 8.dp), verticalAlignment = Alignment.CenterVertically) {
                    IconAction(Icons.Filled.Add, "Пригласить на игру", { pickGame = true })
                    Box(Modifier.weight(1f)) {
                        AppTextField(text, { text = it; sendError = null }, placeholder = "Сообщение…", singleLine = true, maxLength = 2000,
                            imeAction = ImeAction.Send, onImeAction = { })
                    }
                    IconAction(Icons.AutoMirrored.Filled.Send, "Отправить", {
                        val body = text.trim()
                        if (body.isNotEmpty() && !sending) {
                            sending = true
                            scope.launch {
                                val r = container.repo.call { it.sendMessage(otherId, MessageBody(body)) }
                                sending = false
                                when (r) {
                                    is ApiResult.Ok -> { text = ""; merge(listOf(r.value)) }
                                    is ApiResult.Fail -> sendError = r.error.message
                                }
                            }
                        }
                    })
                }
            }
        }
    }

    if (confirmBlock) ConfirmDialog(
        "Заблокировать пользователя?", "Вы перестанете видеть друг друга, дружба и переписка будут прекращены. Разблокировать можно в настройках.",
        "Заблокировать", {
            confirmBlock = false
            scope.launch {
                val r = container.repo.call { it.block(otherId) }
                if (r is ApiResult.Ok) { toaster.show("Пользователь заблокирован"); shell.back() } else if (r is ApiResult.Fail) toaster.show(r.error.message)
            }
        }, { confirmBlock = false }, danger = true,
    )
    if (showReport) ReportDialog("Жалоба на пользователя", userId = otherId, onDismiss = { showReport = false })
    if (pickGame) InviteToGamePicker(otherId, onDismiss = { pickGame = false }, onSent = { merge(emptyList()) })
}

/** «+» в чате: пригласить собеседника в одну из своих открытых игр (организатор). */
@Composable
private fun InviteToGamePicker(otherId: Long, onDismiss: () -> Unit, onSent: () -> Unit) {
    val container = LocalContainer.current
    val toaster = LocalToaster.current
    val scope = rememberCoroutineScope()
    val loader = rememberLoader { container.repo.call { it.games("mine") } }
    val games = loader.value?.items.orEmpty().filter { it.isOrganizer && it.status == "open" }
    when {
        loader.state is Load.Loading -> ru.sportcourts.app.ui.components.AppDialog(onDismiss, "Приглашение на игру", content = {
            Text("Загрузка…", style = AppType.small, color = colors.textSecondary)
        }) { SecondaryButton("Отмена", onDismiss) }
        games.isEmpty() -> ru.sportcourts.app.ui.components.InfoDialog(
            "Нет игр для приглашения",
            if (loader.state is Load.Failed) (loader.state as Load.Failed).error.message else "Приглашать можно в игры, которые вы организуете. Создайте игру в разделе «Игры».",
            onDismiss,
        )
        else -> PickerDialog("В какую игру пригласить?", games, { it.title + " · " + formatGameTime(it.startsAt) }, { g ->
            scope.launch {
                val r = container.repo.call { it.inviteToGame(g.id, InviteBody(listOf(otherId))) }
                when (r) {
                    is ApiResult.Ok -> { toaster.show(if (r.value.sent.isNotEmpty()) "Приглашение отправлено" else "Приглашение не отправлено"); onSent() }
                    is ApiResult.Fail -> toaster.show(r.error.message)
                }
            }
            onDismiss()
        }, onDismiss)
    }
}

@Composable
private fun Bubble(m: Message) {
    val c = colors
    Row(Modifier.fillMaxWidth(), horizontalArrangement = if (m.mine) Arrangement.End else Arrangement.Start) {
        Column(
            Modifier.widthIn(max = 290.dp).clip(RoundedCornerShape(14.dp))
                .background(if (m.mine) c.bubbleMine else c.bubbleOther).padding(horizontal = 12.dp, vertical = 8.dp),
        ) {
            Text(m.body, style = AppType.body, color = if (m.mine) c.onBubbleMine else c.text)
            Text(formatClock(m.createdAt), style = AppType.caption, color = if (m.mine) c.onBubbleMine.copy(alpha = 0.7f) else c.textSecondary,
                modifier = Modifier.align(Alignment.End))
        }
    }
}

// ------------------------------------------------------------------ чужой профиль
@Composable
fun UserProfileScreen(userId: Long) {
    val container = LocalContainer.current
    val shell = LocalShell.current
    val toaster = LocalToaster.current
    val scope = rememberCoroutineScope()
    val loader = rememberLoader(userId) { container.repo.call { it.user(userId) } }
    var confirm by remember { mutableStateOf<String?>(null) }
    var showReport by remember { mutableStateOf(false) }
    val meId = (container.session.value as? ru.sportcourts.app.core.Session.In)?.me?.id

    Screen("Профиль", onBack = { shell.back() }) {
        LoadView(loader, Modifier.fillMaxSize()) { u ->
            FormColumn {
                Column(Modifier.fillMaxWidth(), horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    Avatar(container.repo.mediaUrl(u.avatarUrl), u.displayName, 96.dp, online = if (u.isFriend) u.online else null)
                    Text(u.displayName, style = AppType.title, color = colors.text)
                    Text("@" + u.login, style = AppType.small, color = colors.textSecondary)
                    if (u.isFriend) Text(
                        if (u.online == true) "В сети" else if (u.lastSeenAt != null) "Был(а) в сети ${formatAgo(u.lastSeenAt)}" else "Не в сети",
                        style = AppType.caption, color = if (u.online == true) colors.online else colors.textSecondary,
                    )
                }
                if (u.favoriteSports.isNotEmpty()) {
                    SectionHeader("Любимые виды спорта")
                    ChipFlow { u.favoriteSports.forEach { Tag(it.name) } }
                }
                if (u.id != meId && !u.isSelf) {
                    Spacer(Modifier.padding(top = 8.dp))
                    when {
                        u.blockedByMe -> SecondaryButton("Разблокировать", { scope.launch {
                            val r = container.repo.call { it.unblock(u.id) }
                            if (r is ApiResult.Ok) { toaster.show("Пользователь разблокирован"); loader.load(silent = true) } else if (r is ApiResult.Fail) toaster.show(r.error.message)
                        } })
                        u.isFriend -> {
                            PrimaryButton("Написать сообщение", { shell.navigate("chat/${u.id}") })
                            SecondaryButton("Удалить из друзей", { confirm = "unfriend" }, danger = true)
                        }
                        else -> PrimaryButton("Добавить в друзья", {
                            scope.launch {
                                val r = container.repo.call { it.sendFriendRequest(mapOf("user_id" to u.id)) }
                                when (r) {
                                    is ApiResult.Ok -> { toaster.show(if (r.value.status == "accepted") "Вы теперь друзья" else "Запрос отправлен"); loader.load(silent = true) }
                                    is ApiResult.Fail -> toaster.show(r.error.message)
                                }
                            }
                        })
                    }
                    if (!u.blockedByMe) SecondaryButton("Заблокировать", { confirm = "block" }, danger = true)
                    ru.sportcourts.app.ui.components.TextLink("Пожаловаться", { showReport = true }, color = colors.danger)
                }
            }
        }
    }

    val name = loader.value?.displayName.orEmpty()
    if (confirm == "unfriend") ConfirmDialog("Удалить из друзей?", "$name пропадёт из вашего списка друзей. Переписка станет недоступна.", "Удалить", {
        confirm = null
        scope.launch {
            val r = container.repo.call { it.removeFriend(userId) }
            if (r is ApiResult.Ok) { toaster.show("Удалён из друзей"); loader.load(silent = true) } else if (r is ApiResult.Fail) toaster.show(r.error.message)
        }
    }, { confirm = null }, danger = true)
    if (confirm == "block") ConfirmDialog("Заблокировать пользователя?", "Вы перестанете видеть друг друга, дружба и переписка будут прекращены.", "Заблокировать", {
        confirm = null
        scope.launch {
            val r = container.repo.call { it.block(userId) }
            if (r is ApiResult.Ok) { toaster.show("Пользователь заблокирован"); loader.load(silent = true) } else if (r is ApiResult.Fail) toaster.show(r.error.message)
        }
    }, { confirm = null }, danger = true)
    if (showReport) ReportDialog("Жалоба на пользователя", userId = userId, onDismiss = { showReport = false })
}

// ------------------------------------------------------------------ заблокированные
@Composable
fun BlocksScreen() {
    val container = LocalContainer.current
    val shell = LocalShell.current
    val toaster = LocalToaster.current
    val scope = rememberCoroutineScope()
    val loader = rememberLoader { container.repo.call { it.blocks() } }
    Screen("Заблокированные", onBack = { shell.back() }) {
        LoadView(loader, Modifier.fillMaxSize()) { resp ->
            if (resp.items.isEmpty()) {
                EmptyState("Список пуст", "Вы никого не блокировали.")
            } else LazyColumn(Modifier.fillMaxSize(), contentPadding = PaddingValues(16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                items(resp.items, key = { it.user.id }) { b ->
                    AppCard {
                        Row(verticalAlignment = Alignment.CenterVertically) {
                            Avatar(container.repo.mediaUrl(b.user.avatarUrl), b.user.title(), 40.dp)
                            Spacer(Modifier.width(12.dp))
                            Column(Modifier.weight(1f)) {
                                Text(b.user.title(), style = AppType.bodyBold, color = colors.text, maxLines = 1)
                                Text("@" + b.user.login, style = AppType.caption, color = colors.textSecondary)
                            }
                            Box(Modifier.width(140.dp)) {
                                SecondaryButton("Разблокировать", {
                                    scope.launch {
                                        val r = container.repo.call { it.unblock(b.user.id) }
                                        if (r is ApiResult.Fail) toaster.show(r.error.message)
                                        loader.load(silent = true)
                                    }
                                })
                            }
                        }
                    }
                }
            }
        }
    }
}
