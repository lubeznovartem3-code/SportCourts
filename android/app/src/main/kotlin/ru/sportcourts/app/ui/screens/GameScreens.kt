package ru.sportcourts.app.ui.screens

import android.content.Intent
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Add
import androidx.compose.material.icons.filled.Share
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
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import kotlinx.coroutines.launch
import ru.sportcourts.app.core.ApiResult
import ru.sportcourts.app.data.Friend
import ru.sportcourts.app.data.Game
import ru.sportcourts.app.data.GameBody
import ru.sportcourts.app.data.InviteBody
import ru.sportcourts.app.data.Venue
import ru.sportcourts.app.ui.Load
import ru.sportcourts.app.ui.LoadView
import ru.sportcourts.app.ui.LocalContainer
import ru.sportcourts.app.ui.LocalShell
import ru.sportcourts.app.ui.LocalToaster
import ru.sportcourts.app.ui.components.AppCard
import ru.sportcourts.app.ui.components.AppDialog
import ru.sportcourts.app.ui.components.AppTextField
import ru.sportcourts.app.ui.components.Avatar
import ru.sportcourts.app.ui.components.Chip
import ru.sportcourts.app.ui.components.ChipFlow
import ru.sportcourts.app.ui.components.ConfirmDialog
import ru.sportcourts.app.ui.components.EmptyState
import ru.sportcourts.app.ui.components.FormColumn
import ru.sportcourts.app.ui.components.IconAction
import ru.sportcourts.app.ui.components.InlineError
import ru.sportcourts.app.ui.components.KeyValue
import ru.sportcourts.app.ui.components.PickerDialog
import ru.sportcourts.app.ui.components.PrimaryButton
import ru.sportcourts.app.ui.components.ReportDialog
import ru.sportcourts.app.ui.components.Screen
import ru.sportcourts.app.ui.components.SecondaryButton
import ru.sportcourts.app.ui.components.Tag
import ru.sportcourts.app.ui.components.TabBar
import ru.sportcourts.app.ui.components.TextLink
import ru.sportcourts.app.ui.formatGameTime
import ru.sportcourts.app.ui.plural
import ru.sportcourts.app.ui.rememberLoader
import ru.sportcourts.app.ui.theme.AppType
import ru.sportcourts.app.ui.theme.colors
import java.time.LocalDate
import java.time.LocalTime
import java.time.ZoneId
import java.time.ZonedDateTime
import java.time.format.DateTimeFormatter
import java.util.Locale

// ------------------------------------------------------------------ список игр
@Composable
fun GamesScreen() {
    val container = LocalContainer.current
    val shell = LocalShell.current
    var tab by remember { mutableStateOf(0) }
    val scopes = listOf("open", "mine", "history")
    Screen("Игры", onMenu = { shell.openDrawer() }, actions = {
        IconAction(Icons.Filled.Add, "Создать игру", { shell.navigate("game/new/0") })
    }) {
        Column(Modifier.fillMaxSize()) {
            TabBar(listOf("Открытые", "Мои", "История"), tab, { tab = it })
            val loader = rememberLoader(tab) { container.repo.call { it.games(scopes[tab]) } }
            LoadView(loader, Modifier.weight(1f).fillMaxWidth()) { response ->
                if (response.items.isEmpty()) {
                    EmptyState(
                        when (tab) { 0 -> "Открытых игр нет"; 1 -> "Вы пока не участвуете в играх"; else -> "История пуста" },
                        when (tab) { 0 -> "Создайте игру на любой площадке — другие игроки смогут присоединиться."; 1 -> "Присоединитесь к открытой игре или создайте свою."; else -> "Здесь появятся завершённые и отменённые игры." },
                        action = if (tab != 2) "Создать игру" else null, onAction = { shell.navigate("game/new/0") },
                    )
                } else {
                    LazyColumn(Modifier.fillMaxSize(), contentPadding = PaddingValues(16.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
                        items(response.items, key = { it.id }) { g -> GameCard(g) { shell.navigate("game/${g.id}") } }
                    }
                }
            }
        }
    }
}

@Composable
private fun GameCard(g: Game, onClick: () -> Unit) {
    AppCard(onClick = onClick) {
        Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Text(g.title, style = AppType.bodyBold, color = colors.text, modifier = Modifier.weight(1f), maxLines = 1, overflow = TextOverflow.Ellipsis)
                if (g.status != "open") Tag(if (g.status == "cancelled") "Отменена" else "Завершена")
                else if (g.joined) Tag("Вы в игре")
            }
            Text("${g.venue.name} · ${g.venue.address}", style = AppType.small, color = colors.textSecondary, maxLines = 1, overflow = TextOverflow.Ellipsis)
            Row(verticalAlignment = Alignment.CenterVertically) {
                Text(formatGameTime(g.startsAt), style = AppType.small, color = colors.text, modifier = Modifier.weight(1f))
                Text("${g.participantsCount} / ${g.maxPlayers}", style = AppType.small, color = colors.text)
            }
        }
    }
}

// ------------------------------------------------------------------ создание игры
@Composable
fun CreateGameScreen(initialVenueId: Long) {
    val container = LocalContainer.current
    val shell = LocalShell.current
    val toaster = LocalToaster.current
    val scope = rememberCoroutineScope()
    val venuesLoader = rememberLoader { container.repo.call { it.venues(sort = "name", limit = 200) } }
    var venue by remember { mutableStateOf<Venue?>(null) }
    var title by remember { mutableStateOf("") }
    var dayOffset by remember { mutableStateOf(0) }
    var timeText by remember {
        mutableStateOf(LocalTime.now().plusHours(1).withMinute(0).format(DateTimeFormatter.ofPattern("HH:mm")))
    }
    var players by remember { mutableStateOf(10) }
    var pick by remember { mutableStateOf(false) }
    var busy by remember { mutableStateOf(false) }
    var error by remember { mutableStateOf<String?>(null) }

    LaunchedEffect(venuesLoader.value) {
        val list = venuesLoader.value?.items ?: return@LaunchedEffect
        if (venue == null && initialVenueId > 0) venue = list.firstOrNull { it.id == initialVenueId }
    }

    Screen("Новая игра", onBack = { shell.back() }) {
        FormColumn {
            Text("Площадка", style = AppType.caption, color = colors.text)
            Row(
                Modifier.fillMaxWidth().clip(RoundedCornerShape(10.dp)).border(1.dp, colors.border, RoundedCornerShape(10.dp))
                    .clickable { pick = true }.padding(14.dp),
            ) {
                Text(venue?.name ?: "Выберите площадку", style = AppType.body, color = if (venue == null) colors.textSecondary else colors.text, modifier = Modifier.weight(1f))
                Text("Изменить", style = AppType.caption, color = colors.textSecondary)
            }
            AppTextField(title, { title = it }, label = "Название игры", placeholder = "Например, Вечерний баскетбол", maxLength = 80)

            Text("День", style = AppType.caption, color = colors.text)
            val today = LocalDate.now()
            val dayFmt = DateTimeFormatter.ofPattern("EEE, d MMM", Locale("ru"))
            Row(Modifier.horizontalScroll(rememberScrollState()), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                for (i in 0..6) {
                    val label = when (i) { 0 -> "Сегодня"; 1 -> "Завтра"; else -> today.plusDays(i.toLong()).format(dayFmt) }
                    Chip(label, dayOffset == i, { dayOffset = i })
                }
            }
            AppTextField(timeText, { timeText = it.filter { ch -> ch.isDigit() || ch == ':' }.take(5) }, label = "Время начала (ЧЧ:ММ)",
                placeholder = "18:00", keyboardType = KeyboardType.Number, imeAction = ImeAction.Done)

            Text("Максимум игроков (включая вас)", style = AppType.caption, color = colors.text)
            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(16.dp)) {
                Chip("−", false, { if (players > 2) players-- })
                Text("$players", style = AppType.title, color = colors.text)
                Chip("+", false, { if (players < 100) players++ })
            }
            InlineError(error)
            PrimaryButton("Создать игру", {
                error = null
                val v = venue
                val time = try { LocalTime.parse(timeText.padStart(5, '0'), DateTimeFormatter.ofPattern("HH:mm")) } catch (e: Exception) { null }
                when {
                    v == null -> error = "Выберите площадку"
                    title.isBlank() -> error = "Введите название игры"
                    time == null -> error = "Время укажите в формате ЧЧ:ММ, например 18:30"
                    else -> {
                        val start = ZonedDateTime.of(today.plusDays(dayOffset.toLong()), time, ZoneId.systemDefault())
                        if (!start.isAfter(ZonedDateTime.now())) {
                            error = "Время начала уже прошло"
                        } else {
                            busy = true
                            scope.launch {
                                val r = container.repo.call { it.createGame(GameBody(v.id, title.trim(), start.toInstant().toString(), players)) }
                                busy = false
                                when (r) {
                                    is ApiResult.Ok -> { toaster.show("Игра создана"); shell.back(); shell.navigate("game/${r.value.id}") }
                                    is ApiResult.Fail -> error = r.error.message
                                }
                            }
                        }
                    }
                }
            }, loading = busy)
        }
    }

    if (pick) {
        val list = venuesLoader.value?.items.orEmpty()
        if (list.isEmpty()) {
            AppDialog({ pick = false }, "Площадка", content = {
                Text("Площадок пока нет или список не загрузился.", style = AppType.small, color = colors.textSecondary)
            }) { SecondaryButton("Закрыть", { pick = false }) }
        } else {
            PickerDialog("Площадка", list, { it.name + " — " + it.address }, { venue = it; pick = false }, { pick = false })
        }
    }
}

// ------------------------------------------------------------------ сбор состава
@Composable
fun GameScreen(gameId: Long) {
    val container = LocalContainer.current
    val shell = LocalShell.current
    val toaster = LocalToaster.current
    val scope = rememberCoroutineScope()
    val context = LocalContext.current
    val loader = rememberLoader(gameId) { container.repo.call { it.game(gameId) } }
    var busy by remember { mutableStateOf(false) }
    var error by remember { mutableStateOf<String?>(null) }
    var confirm by remember { mutableStateOf<String?>(null) }
    var showInvite by remember { mutableStateOf(false) }
    var showReport by remember { mutableStateOf(false) }

    fun act(call: suspend (ru.sportcourts.app.data.Api) -> Game, doneMessage: String?) {
        busy = true
        error = null
        scope.launch {
            val r = container.repo.call { call(it) }
            busy = false
            when (r) {
                is ApiResult.Ok -> { loader.set(r.value); if (doneMessage != null) toaster.show(doneMessage) }
                is ApiResult.Fail -> { error = r.error.message; loader.load(silent = true) }
            }
        }
    }

    val g = loader.value
    Screen(
        "Сбор состава", onBack = { shell.back() },
        actions = {
            if (g != null) IconAction(Icons.Filled.Share, "Поделиться", {
                val text = "Играем: ${g.title}. ${g.venue.name}, ${g.venue.address}. ${formatGameTime(g.startsAt)}. Мест: ${g.maxPlayers}. Присоединяйтесь в SportCourts!"
                val send = Intent(Intent.ACTION_SEND).apply { type = "text/plain"; putExtra(Intent.EXTRA_TEXT, text) }
                context.startActivity(Intent.createChooser(send, "Поделиться игрой"))
            })
        },
    ) {
        LoadView(loader, Modifier.fillMaxSize()) { game ->
            FormColumn {
                AppCard {
                    Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                        Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                            game.venue.sports.firstOrNull()?.let { Tag(it.name) }
                            if (game.status != "open") Tag(if (game.status == "cancelled") "Игра отменена" else "Игра завершена")
                        }
                        Text(game.title, style = AppType.title, color = colors.text)
                        Text("${game.venue.name}, ${game.venue.address}", style = AppType.small, color = colors.textSecondary)
                        Row(Modifier.fillMaxWidth().padding(top = 6.dp), horizontalArrangement = Arrangement.SpaceBetween) {
                            KeyValue("Когда играем", formatGameTime(game.startsAt), Modifier.weight(1f))
                            KeyValue("Организатор", game.organizer.displayName.ifEmpty { game.organizer.login } + if (game.isOrganizer) " (Вы)" else "", Modifier.weight(1f))
                        }
                    }
                }
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Text("Состав команды", style = AppType.bodyBold, color = colors.text, modifier = Modifier.weight(1f))
                    Text("${game.participantsCount} / ${game.maxPlayers} ${plural(game.maxPlayers, "игрок", "игрока", "игроков")}", style = AppType.small, color = colors.textSecondary)
                }
                game.participants.forEach { p ->
                    val name = p.user.displayName.ifEmpty { p.user.login }
                    Row(
                        Modifier.fillMaxWidth().clickable { shell.navigate("user/${p.user.id}") }.padding(vertical = 4.dp),
                        verticalAlignment = Alignment.CenterVertically,
                    ) {
                        Avatar(container.repo.mediaUrl(p.user.avatarUrl), name, 40.dp)
                        Spacer(Modifier.width(12.dp))
                        Text(name, style = AppType.body, color = colors.text, modifier = Modifier.weight(1f), maxLines = 1, overflow = TextOverflow.Ellipsis)
                        Text(if (p.isOrganizer) "Создатель" else "Готов", style = AppType.caption, color = colors.textSecondary)
                    }
                }
                // свободные места показываем рамками, но не больше восьми — чтобы список не растягивался на игры в 100 мест
                val shownFree = if (game.status == "open") game.freeSlots.coerceAtMost(8) else 0
                repeat(shownFree) {
                    Box(
                        Modifier.fillMaxWidth().clip(RoundedCornerShape(8.dp)).border(1.dp, colors.border, RoundedCornerShape(8.dp)).padding(12.dp),
                    ) { Text("+ Ожидание игрока…", style = AppType.small, color = colors.textSecondary) }
                }
                if (game.freeSlots > shownFree && game.status == "open") {
                    Text("и ещё ${game.freeSlots - shownFree} свободных мест", style = AppType.caption, color = colors.textSecondary)
                }
                InlineError(error)
                if (game.status == "open") {
                    when {
                        game.isOrganizer -> {
                            PrimaryButton("Пригласить друзей", { showInvite = true })
                            SecondaryButton("Завершить игру", { confirm = "finish" })
                            SecondaryButton("Отменить игру", { confirm = "cancel" }, danger = true)
                        }
                        game.joined -> SecondaryButton("Покинуть лобби", { confirm = "leave" })
                        game.freeSlots > 0 -> PrimaryButton("Присоединиться", { act({ api -> api.joinGame(game.id) }, "Вы в игре") }, loading = busy)
                        else -> Text("Свободных мест нет.", style = AppType.small, color = colors.textSecondary)
                    }
                }
                if (!game.isOrganizer) TextLink("Пожаловаться на игру", { showReport = true }, color = colors.danger)
            }
        }
    }

    when (confirm) {
        "leave" -> ConfirmDialog("Покинуть лобби?", "Ваше место освободится для других игроков.", "Покинуть", {
            confirm = null; act({ api -> api.leaveGame(gameId) }, "Вы вышли из игры")
        }, { confirm = null })
        "cancel" -> ConfirmDialog("Отменить игру?", "Игра будет закрыта для всех участников. Это нельзя отменить.", "Отменить игру", {
            confirm = null; act({ api -> api.cancelGame(gameId) }, "Игра отменена")
        }, { confirm = null }, danger = true, dismissText = "Назад")
        "finish" -> ConfirmDialog("Завершить игру?", "Игра перейдёт в историю.", "Завершить", {
            confirm = null; act({ api -> api.finishGame(gameId) }, "Игра завершена")
        }, { confirm = null })
    }
    if (showInvite) InviteDialog(gameId, onDismiss = { showInvite = false })
    if (showReport) ReportDialog("Жалоба на игру", gameId = gameId, onDismiss = { showReport = false })
}

@Composable
private fun InviteDialog(gameId: Long, onDismiss: () -> Unit) {
    val container = LocalContainer.current
    val toaster = LocalToaster.current
    val scope = rememberCoroutineScope()
    val friends = rememberLoader { container.repo.call { it.friends() } }
    var chosen by remember { mutableStateOf(setOf<Long>()) }
    var busy by remember { mutableStateOf(false) }
    var error by remember { mutableStateOf<String?>(null) }
    AppDialog(onDismiss, "Пригласить друзей", content = {
        when (val s = friends.state) {
            is Load.Loading -> Text("Загрузка…", style = AppType.small, color = colors.textSecondary)
            is Load.Failed -> InlineError(s.error.message)
            is Load.Ready -> if (s.value.items.isEmpty()) {
                Text("У вас пока нет друзей. Добавьте их в разделе «Друзья».", style = AppType.small, color = colors.textSecondary)
            } else {
                Text("Приглашение придёт в личные сообщения.", style = AppType.caption, color = colors.textSecondary)
                Column(Modifier.heightIn(max = 300.dp).verticalScroll(rememberScrollState()), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    ChipFlow {
                        s.value.items.forEach { f ->
                            val name = f.displayName.ifEmpty { f.login }
                            Chip(name, f.id in chosen, { chosen = if (f.id in chosen) chosen - f.id else chosen + f.id })
                        }
                    }
                }
            }
        }
        InlineError(error)
    }) {
        Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
            PrimaryButton("Отправить приглашения", {
                busy = true
                scope.launch {
                    val r = container.repo.call { it.inviteToGame(gameId, InviteBody(chosen.toList())) }
                    busy = false
                    when (r) {
                        is ApiResult.Ok -> {
                            toaster.show("Отправлено: ${r.value.sent.size}" + if (r.value.skipped.isNotEmpty()) ", пропущено: ${r.value.skipped.size}" else "")
                            onDismiss()
                        }
                        is ApiResult.Fail -> error = r.error.message
                    }
                }
            }, enabled = chosen.isNotEmpty(), loading = busy)
            SecondaryButton("Закрыть", onDismiss)
        }
    }
}
