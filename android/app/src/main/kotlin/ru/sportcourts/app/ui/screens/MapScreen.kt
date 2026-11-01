package ru.sportcourts.app.ui.screens

import android.Manifest
import androidx.activity.compose.BackHandler
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Add
import androidx.compose.material.icons.filled.Place
import androidx.compose.material.icons.filled.Search
import androidx.compose.material3.Icon
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
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.LocalConfiguration
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.compose.LocalLifecycleOwner
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.lifecycle.repeatOnLifecycle
import coil3.compose.AsyncImage
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import ru.sportcourts.app.core.ApiResult
import ru.sportcourts.app.data.Game
import ru.sportcourts.app.data.PlayerReportBody
import ru.sportcourts.app.data.Venue
import ru.sportcourts.app.ui.Load
import ru.sportcourts.app.ui.LocalContainer
import ru.sportcourts.app.ui.LocalMapKitReady
import ru.sportcourts.app.ui.LocalShell
import ru.sportcourts.app.ui.LocalToaster
import ru.sportcourts.app.ui.components.AppCard
import ru.sportcourts.app.ui.components.AppDialog
import ru.sportcourts.app.ui.components.AppTextField
import ru.sportcourts.app.ui.components.Chip
import ru.sportcourts.app.ui.components.ConfirmDialog
import ru.sportcourts.app.ui.components.Divider
import ru.sportcourts.app.ui.components.EmptyState
import ru.sportcourts.app.ui.components.ErrorState
import ru.sportcourts.app.ui.components.IconAction
import ru.sportcourts.app.ui.components.InlineError
import ru.sportcourts.app.ui.components.KeyValue
import ru.sportcourts.app.ui.components.LoadingBox
import ru.sportcourts.app.ui.components.PrimaryButton
import ru.sportcourts.app.ui.components.ReportDialog
import ru.sportcourts.app.ui.components.SecondaryButton
import ru.sportcourts.app.ui.components.Tag
import ru.sportcourts.app.ui.components.TextLink
import ru.sportcourts.app.ui.components.TopBar
import ru.sportcourts.app.ui.containerViewModel
import ru.sportcourts.app.ui.formatAgo
import ru.sportcourts.app.ui.formatClock
import ru.sportcourts.app.ui.formatDistance
import ru.sportcourts.app.ui.formatGameTime
import ru.sportcourts.app.ui.map.GeoPoint
import ru.sportcourts.app.ui.map.MapViewModel
import ru.sportcourts.app.ui.map.YandexMap
import ru.sportcourts.app.ui.map.hasLocationPermission
import ru.sportcourts.app.ui.map.requestSingleLocation
import ru.sportcourts.app.ui.minutesLeft
import ru.sportcourts.app.ui.playersNow
import ru.sportcourts.app.ui.plural
import ru.sportcourts.app.ui.theme.AppType
import ru.sportcourts.app.ui.theme.colors
import ru.sportcourts.app.ui.venueTypeName

@Composable
fun MapScreen() {
    val container = LocalContainer.current
    val shell = LocalShell.current
    val context = LocalContext.current
    val mapKitReady = LocalMapKitReady.current
    val vm = containerViewModel { MapViewModel(it, startInList = !mapKitReady) }
    val settings by container.settings.collectAsStateWithLifecycle()
    val scope = rememberCoroutineScope()
    val lifecycleOwner = LocalLifecycleOwner.current
    var longTapPoint by remember { mutableStateOf<GeoPoint?>(null) }

    val permissionLauncher = rememberLauncherForActivityResult(ActivityResultContracts.RequestMultiplePermissions()) { grants ->
        if (grants.values.any { it }) requestSingleLocation(context) { vm.onLocation(it) } else vm.onLocation(null)
    }

    fun locate() {
        if (hasLocationPermission(context)) requestSingleLocation(context) { vm.onLocation(it) }
        else permissionLauncher.launch(arrayOf(Manifest.permission.ACCESS_FINE_LOCATION, Manifest.permission.ACCESS_COARSE_LOCATION))
    }

    LaunchedEffect(Unit) {
        vm.loadSports()
        if (vm.location == null) locate()
    }

    // Фильтры и поиск: перезагрузка с небольшой задержкой, чтобы не слать запрос на каждую букву
    LaunchedEffect(vm.query, vm.sportId, vm.venueType, vm.minPlayers, vm.sort, settings?.refLat, settings?.refLon) {
        if (vm.query.isNotBlank()) delay(350)
        vm.reload(silent = vm.venues is Load.Ready)
    }

    // Пока экран открыт, раз в 30 секунд обновляем число игроков
    LaunchedEffect(Unit) {
        lifecycleOwner.lifecycle.repeatOnLifecycle(Lifecycle.State.STARTED) {
            while (true) {
                delay(30_000)
                vm.reload(silent = true)
                vm.selected?.let { s ->
                    val o = vm.origin()
                    val r = container.repo.call { it.venue(s.id, o?.lat, o?.lon) }
                    if (r is ApiResult.Ok && vm.selected?.id == s.id) vm.selected = r.value
                }
            }
        }
    }

    BackHandler(enabled = vm.selected != null) { vm.selected = null }

    val dark = colors.dark
    Column(Modifier.fillMaxSize().background(colors.background)) {
        TopBar(
            "Карта площадок", onMenu = { shell.openDrawer() },
            actions = {
                IconAction(Icons.Filled.Search, "Поиск и фильтры", { vm.searchOpen = !vm.searchOpen })
                IconAction(Icons.Filled.Add, "Предложить площадку", { shell.navigate("venue/new") })
            },
        )
        if (vm.searchOpen) SearchPanel(vm)
        Box(Modifier.weight(1f).fillMaxWidth()) {
            if (vm.listMode) {
                VenueList(vm)
            } else if (mapKitReady) {
                val list = (vm.venues as? Load.Ready)?.value.orEmpty()
                YandexMap(
                    venues = list,
                    selectedId = vm.selected?.id,
                    me = vm.location,
                    reference = settings?.let { s -> if (s.refLat != null && s.refLon != null) GeoPoint(s.refLat, s.refLon) else null },
                    dark = dark,
                    camera = vm.camera,
                    onSelect = { vm.select(it) },
                    onLongTap = { longTapPoint = it },
                    onEmptyTap = { vm.selected = null },
                    modifier = Modifier.fillMaxSize(),
                )
                MapOverlay(vm, onLocate = { locate() })
            } else {
                EmptyState(
                    "Карта недоступна", "При сборке не задан ключ MapKit (MAPKIT_API_KEY в файле local.properties). " +
                        "Список площадок работает — переключитесь на него.", mark = "!",
                    action = "Открыть список", onAction = { vm.listMode = true },
                )
            }
            // переключатель карта / список
            Row(Modifier.align(Alignment.TopEnd).padding(12.dp)) {
                Row(Modifier.clip(RoundedCornerShape(18.dp)).background(colors.background).border(1.dp, colors.border, RoundedCornerShape(18.dp))) {
                    Chip("Карта", !vm.listMode, { vm.listMode = false })
                    Chip("Список", vm.listMode, { vm.listMode = true })
                }
            }
            val selected = vm.selected
            if (selected != null) {
                Box(Modifier.align(Alignment.BottomCenter)) {
                    VenueSheet(selected, vm, onClose = { vm.selected = null })
                }
            }
        }
    }

    longTapPoint?.let { p ->
        ConfirmDialog(
            title = "Точка отсчёта",
            text = "Считать расстояния до площадок от этой точки на карте? Её можно сбросить в любой момент.",
            confirmText = "Задать точку",
            onConfirm = { vm.setReferencePoint(p); longTapPoint = null; vm.sort = "distance" },
            onDismiss = { longTapPoint = null },
        )
    }
}

@Composable
private fun MapOverlay(vm: MapViewModel, onLocate: () -> Unit) {
    val container = LocalContainer.current
    val settings by container.settings.collectAsStateWithLifecycle()
    val scope = rememberCoroutineScope()
    Box(Modifier.fillMaxSize()) {
        Column(Modifier.align(Alignment.TopStart).padding(12.dp).fillMaxWidth(0.65f), verticalArrangement = Arrangement.spacedBy(6.dp)) {
            val hasRef = settings?.refLat != null
            if (hasRef) {
                OverlayPill("Точка отсчёта выбрана · Сбросить") { vm.setReferencePoint(null) }
            }
            vm.locationNote?.let { OverlayPill(it, null) }
            if (vm.venues is Load.Failed) OverlayPill("Не удалось обновить площадки · Повторить") { vm.reload() }
        }
        Box(
            Modifier.align(Alignment.BottomEnd).padding(end = 12.dp, bottom = if (vm.selected != null) 240.dp else 20.dp).size(46.dp)
                .clip(CircleShape).background(colors.background).border(1.dp, colors.border, CircleShape)
                .clickable { onLocate() },
            contentAlignment = Alignment.Center,
        ) { Icon(Icons.Filled.Place, "Моё местоположение", tint = colors.text) }
    }
}

@Composable
private fun OverlayPill(text: String, onClick: (() -> Unit)?) {
    val m = Modifier.clip(RoundedCornerShape(10.dp)).background(colors.background).border(1.dp, colors.border, RoundedCornerShape(10.dp))
    Box((if (onClick != null) m.clickable(onClick = onClick) else m).padding(horizontal = 10.dp, vertical = 7.dp)) {
        Text(text, style = AppType.caption, color = colors.text)
    }
}

// ------------------------------------------------------------------ поиск и фильтры
@Composable
private fun SearchPanel(vm: MapViewModel) {
    Column(Modifier.fillMaxWidth().background(colors.background).padding(horizontal = 16.dp, vertical = 10.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
        AppTextField(vm.query, { vm.query = it }, placeholder = "Название или адрес площадки", imeAction = ImeAction.Search, maxLength = 100)
        Row(Modifier.horizontalScroll(rememberScrollState()), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            Chip("Все виды спорта", vm.sportId == null, { vm.sportId = null })
            vm.sports.forEach { s -> Chip(s.name, vm.sportId == s.id, { vm.sportId = if (vm.sportId == s.id) null else s.id }) }
        }
        Row(Modifier.horizontalScroll(rememberScrollState()), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            Chip("Любая", vm.venueType == null, { vm.venueType = null })
            Chip("Открытая", vm.venueType == "outdoor", { vm.venueType = "outdoor" })
            Chip("Закрытая", vm.venueType == "indoor", { vm.venueType = "indoor" })
            Spacer(Modifier.width(8.dp))
            Chip("Любое число игроков", vm.minPlayers == null, { vm.minPlayers = null })
            Chip("От 2", vm.minPlayers == 2, { vm.minPlayers = 2 })
            Chip("От 6", vm.minPlayers == 6, { vm.minPlayers = 6 })
            Chip("От 10", vm.minPlayers == 10, { vm.minPlayers = 10 })
        }
        Row(Modifier.horizontalScroll(rememberScrollState()), horizontalArrangement = Arrangement.spacedBy(8.dp), verticalAlignment = Alignment.CenterVertically) {
            Text("Сортировка:", style = AppType.caption, color = colors.textSecondary)
            Chip("Ближайшие", vm.sort == "distance", { vm.sort = "distance" })
            Chip("По названию", vm.sort == "name", { vm.sort = "name" })
            Chip("По числу игроков", vm.sort == "players", { vm.sort = "players" })
        }
        Divider()
    }
}

// ------------------------------------------------------------------ список площадок
@Composable
private fun VenueList(vm: MapViewModel) {
    when (val s = vm.venues) {
        is Load.Loading -> LoadingBox()
        is Load.Failed -> ErrorState(s.error, onRetry = { vm.reload() })
        is Load.Ready -> if (s.value.isEmpty()) {
            val filtered = vm.query.isNotBlank() || vm.activeFilters > 0
            EmptyState(
                if (filtered) "Ничего не найдено" else "Площадок пока нет",
                if (filtered) "Измените запрос или сбросьте фильтры." else "Предложите первую площадку — после проверки модератором она появится на карте.",
            )
        } else LazyColumn(Modifier.fillMaxSize(), contentPadding = androidx.compose.foundation.layout.PaddingValues(start = 16.dp, end = 16.dp, top = 64.dp, bottom = 260.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
            items(s.value, key = { it.id }) { v ->
                AppCard(onClick = { vm.select(v); vm.moveCamera(v.latitude, v.longitude, 15f) }) {
                    Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
                        Row(verticalAlignment = Alignment.CenterVertically) {
                            Text(v.name, style = AppType.bodyBold, color = colors.text, modifier = Modifier.weight(1f), maxLines = 1, overflow = TextOverflow.Ellipsis)
                            formatDistance(v.distanceKm)?.let { Text(it, style = AppType.small, color = colors.textSecondary) }
                        }
                        Text(v.address, style = AppType.small, color = colors.textSecondary, maxLines = 2, overflow = TextOverflow.Ellipsis)
                        Row(horizontalArrangement = Arrangement.spacedBy(6.dp), verticalAlignment = Alignment.CenterVertically) {
                            v.sports.take(3).forEach { Tag(it.name) }
                            Tag(venueTypeName(v.venueType))
                            Spacer(Modifier.weight(1f))
                            Text("Игроков: ${v.playersNow()}", style = AppType.caption, color = colors.text)
                        }
                    }
                }
            }
        }
    }
}

// ------------------------------------------------------------------ карточка площадки
@Composable
private fun VenueSheet(venue: Venue, vm: MapViewModel, onClose: () -> Unit) {
    val container = LocalContainer.current
    val shell = LocalShell.current
    val toaster = LocalToaster.current
    val scope = rememberCoroutineScope()
    val c = colors
    var expanded by remember(venue.id) { mutableStateOf(false) }
    var busy by remember(venue.id) { mutableStateOf(false) }
    var showPlayers by remember { mutableStateOf(false) }
    var showReport by remember { mutableStateOf(false) }
    var showReports by remember { mutableStateOf(false) }
    var error by remember(venue.id) { mutableStateOf<String?>(null) }
    val maxHeight = (LocalConfiguration.current.screenHeightDp * 0.7f).dp
    val me = container.session.collectAsStateWithLifecycle().value

    val games = remember(venue.id) { mutableStateOf<List<Game>?>(null) }
    LaunchedEffect(venue.id, expanded) {
        if (expanded) {
            val r = container.repo.call { it.games("open", venue.id) }
            games.value = (r as? ApiResult.Ok)?.value?.items
        }
    }

    Column(
        Modifier.fillMaxWidth().heightIn(max = maxHeight)
            .clip(RoundedCornerShape(topStart = 20.dp, topEnd = 20.dp)).background(c.background)
            .border(1.dp, c.border, RoundedCornerShape(topStart = 20.dp, topEnd = 20.dp)),
    ) {
        Box(Modifier.fillMaxWidth().clickable { expanded = !expanded }.padding(top = 10.dp, bottom = 6.dp), contentAlignment = Alignment.Center) {
            Box(Modifier.width(40.dp).height(4.dp).clip(RoundedCornerShape(2.dp)).background(c.border))
        }
        Column(
            Modifier.weight(1f, fill = false).verticalScroll(rememberScrollState()).padding(horizontal = 20.dp).padding(bottom = 4.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            Row(verticalAlignment = Alignment.Top) {
                Column(Modifier.weight(1f)) {
                    Text(venue.name, style = AppType.title, color = c.text)
                    Spacer(Modifier.height(2.dp))
                    Text(venue.address, style = AppType.small, color = c.textSecondary)
                    formatDistance(venue.distanceKm)?.let { Text("$it от точки отсчёта", style = AppType.caption, color = c.textSecondary) }
                }
                venue.sports.firstOrNull()?.let { Tag(it.name + if (venue.sports.size > 1) " +${venue.sports.size - 1}" else "") }
            }
            if (venue.photoUrl != null) {
                AsyncImage(
                    model = container.repo.mediaUrl(venue.photoUrl), contentDescription = "Фотография площадки",
                    contentScale = ContentScale.Crop,
                    modifier = Modifier.fillMaxWidth().height(if (expanded) 190.dp else 120.dp).clip(RoundedCornerShape(12.dp)).background(c.surface),
                )
            }

            val presence = venue.myPresence
            val active = presence?.active == true
            val left = minutesLeft(presence?.expiresAt)
            PrimaryButton(
                if (active) "Я ушёл(а) с площадки" else "Играть", {
                    busy = true
                    error = null
                    scope.launch {
                        val r = container.repo.call { it.togglePresence(venue.id) }
                        busy = false
                        when (r) {
                            is ApiResult.Ok -> {
                                vm.selected = venue.copy(
                                    myPresence = ru.sportcourts.app.data.MyPresence(r.value.active, r.value.expiresAt),
                                    checkedInCount = r.value.checkedInCount,
                                )
                                vm.reload(silent = true)
                                toaster.show(if (r.value.active) "Вы отмечены на площадке на 3 часа" else "Отметка снята")
                            }
                            is ApiResult.Fail -> error = r.error.message
                        }
                    }
                }, loading = busy,
            )
            if (active && left != null) {
                Text(
                    "Вы на площадке. Отметка снимется автоматически через ${left / 60} ч ${left % 60} мин.",
                    style = AppType.caption, color = c.textSecondary,
                )
            } else {
                Text("Отметка «Играю» действует 3 часа и видна другим игрокам.", style = AppType.caption, color = c.textSecondary)
            }
            InlineError(error)

            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                val now = venue.playersNow()
                KeyValue("Игроки", "$now ${plural(now, "человек", "человека", "человек")}", Modifier.weight(1f))
                KeyValue("Время работы", venue.workHours ?: "не указано", Modifier.weight(1f))
                KeyValue("Стоимость", venue.costInfo ?: "не указана", Modifier.weight(1f))
            }
            val report = venue.latestReport
            if (report != null) {
                Text(
                    "Сообщили игроков: ${report.playerCount} (${formatClock(report.reportedAt)}, ${formatAgo(report.reportedAt)})" +
                        if (!report.isFresh) " — данные устарели" else "",
                    style = AppType.caption, color = c.textSecondary,
                )
            }
            Text("Отметились на площадке: ${venue.checkedInCount}", style = AppType.caption, color = c.textSecondary)

            if (expanded) {
                Divider()
                if (!venue.description.isNullOrBlank()) Text(venue.description, style = AppType.small, color = c.text)
                Text("Тип: ${venueTypeName(venue.venueType)} · ${venue.sports.joinToString { it.name }.ifEmpty { "виды спорта не указаны" }}", style = AppType.small, color = c.textSecondary)
                SecondaryButton("Сообщить, сколько здесь игроков", { showPlayers = true })
                TextLink("Кто сообщал о числе игроков", { showReports = true })

                Text("Открытые игры", style = AppType.bodyBold, color = c.text)
                val g = games.value
                when {
                    g == null -> Text("Загрузка…", style = AppType.small, color = c.textSecondary)
                    g.isEmpty() -> Text("Пока нет открытых игр. Создайте свою — друзья получат приглашение.", style = AppType.small, color = c.textSecondary)
                    else -> g.forEach { game ->
                        Row(
                            Modifier.fillMaxWidth().clip(RoundedCornerShape(10.dp)).border(1.dp, c.border, RoundedCornerShape(10.dp))
                                .clickable { shell.navigate("game/${game.id}") }.padding(12.dp),
                            verticalAlignment = Alignment.CenterVertically,
                        ) {
                            Column(Modifier.weight(1f)) {
                                Text(game.title, style = AppType.bodyBold, color = c.text, maxLines = 1, overflow = TextOverflow.Ellipsis)
                                Text(formatGameTime(game.startsAt), style = AppType.caption, color = c.textSecondary)
                            }
                            Text("${game.participantsCount} / ${game.maxPlayers}", style = AppType.small, color = c.text)
                        }
                    }
                }
                SecondaryButton("Создать игру здесь", { shell.navigate("game/new/${venue.id}") })
                Divider()
                val isAdmin = (me as? ru.sportcourts.app.core.Session.In)?.me?.isAdmin == true
                SecondaryButton(if (isAdmin) "Изменить площадку" else "Предложить изменения", { shell.navigate("venue/edit/${venue.id}") })
                TextLink("Пожаловаться на площадку", { showReport = true }, color = c.danger)
            } else {
                TextLink("Подробнее", { expanded = true })
            }
            Spacer(Modifier.height(8.dp))
        }
        Spacer(Modifier.navigationBarsPadding())
    }

    if (showPlayers) PlayerCountDialog(venue, onDismiss = { showPlayers = false }, onDone = { vm.reload(silent = true); vm.select(venue) })
    if (showReport) ReportDialog("Жалоба на площадку", venueId = venue.id, onDismiss = { showReport = false })
    if (showReports) PlayerReportsDialog(venue.id, onDismiss = { showReports = false })
}

@Composable
private fun PlayerCountDialog(venue: Venue, onDismiss: () -> Unit, onDone: () -> Unit) {
    val container = LocalContainer.current
    val toaster = LocalToaster.current
    val scope = rememberCoroutineScope()
    var text by remember { mutableStateOf("") }
    var busy by remember { mutableStateOf(false) }
    var error by remember { mutableStateOf<String?>(null) }
    AppDialog(onDismiss, "Сколько игроков?", content = {
        Text("Укажите, сколько человек сейчас на площадке «${venue.name}». Это не отметка присутствия — просто сообщение для других.", style = AppType.small, color = colors.textSecondary)
        AppTextField(text, { text = it.filter { ch -> ch.isDigit() }.take(3); error = null }, placeholder = "Например, 8",
            keyboardType = KeyboardType.Number, imeAction = ImeAction.Done)
        InlineError(error)
    }) {
        Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
            PrimaryButton("Отправить", {
                val n = text.toIntOrNull()
                if (n == null || n > 200) { error = "Введите число от 0 до 200" } else {
                    busy = true
                    scope.launch {
                        val r = container.repo.call { it.reportPlayers(venue.id, PlayerReportBody(n)) }
                        busy = false
                        when (r) {
                            is ApiResult.Ok -> { toaster.show("Спасибо! Данные обновлены"); onDone(); onDismiss() }
                            is ApiResult.Fail -> error = r.error.message
                        }
                    }
                }
            }, loading = busy)
            SecondaryButton("Отмена", onDismiss)
        }
    }
}

@Composable
private fun PlayerReportsDialog(venueId: Long, onDismiss: () -> Unit) {
    val container = LocalContainer.current
    var items by remember { mutableStateOf<Load<List<ru.sportcourts.app.data.PlayerReportItem>>>(Load.Loading) }
    LaunchedEffect(venueId) {
        items = when (val r = container.repo.call { it.playerReports(venueId) }) {
            is ApiResult.Ok -> Load.Ready(r.value.items)
            is ApiResult.Fail -> Load.Failed(r.error)
        }
    }
    AppDialog(onDismiss, "Последние сообщения", content = {
        when (val s = items) {
            is Load.Loading -> Text("Загрузка…", style = AppType.small, color = colors.textSecondary)
            is Load.Failed -> InlineError(s.error.message)
            is Load.Ready -> if (s.value.isEmpty()) Text("Пока никто не сообщал.", style = AppType.small, color = colors.textSecondary)
            else Column(Modifier.heightIn(max = 300.dp).verticalScroll(rememberScrollState()), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                s.value.forEach {
                    Text("${it.playerCount} чел. — ${it.reporter.displayName.ifEmpty { it.reporter.login }}, ${formatAgo(it.reportedAt)}", style = AppType.small, color = colors.text)
                }
            }
        }
    }) { SecondaryButton("Закрыть", onDismiss) }
}
