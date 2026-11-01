package ru.sportcourts.app.ui.screens

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import kotlinx.coroutines.launch
import ru.sportcourts.app.core.ApiResult
import ru.sportcourts.app.core.normalizeServerUrl
import ru.sportcourts.app.data.ChangePasswordBody
import ru.sportcourts.app.data.LoginBody
import ru.sportcourts.app.data.RegisterBody
import ru.sportcourts.app.ui.LocalContainer
import ru.sportcourts.app.ui.Validation
import ru.sportcourts.app.ui.components.AppDialog
import ru.sportcourts.app.ui.components.AppTextField
import ru.sportcourts.app.ui.components.InlineError
import ru.sportcourts.app.ui.components.PrimaryButton
import ru.sportcourts.app.ui.components.SecondaryButton
import ru.sportcourts.app.ui.components.TextLink
import ru.sportcourts.app.ui.theme.AppType
import ru.sportcourts.app.ui.theme.colors

@Composable
fun AuthScreen() {
    val container = LocalContainer.current
    val scope = rememberCoroutineScope()
    val settings by container.settings.collectAsState()
    val notice by container.notice.collectAsState()
    var register by remember { mutableStateOf(false) }
    var login by remember { mutableStateOf("") }
    var password by remember { mutableStateOf("") }
    var repeat by remember { mutableStateOf("") }
    var busy by remember { mutableStateOf(false) }
    var error by remember { mutableStateOf<String?>(null) }
    var loginError by remember { mutableStateOf<String?>(null) }
    var passwordError by remember { mutableStateOf<String?>(null) }
    var repeatError by remember { mutableStateOf<String?>(null) }
    var showServer by remember { mutableStateOf(false) }
    val serverUrl = settings?.apiUrl.orEmpty()

    fun submit() {
        if (busy) return
        error = null
        loginError = Validation.login(login).takeIf { register }
        passwordError = Validation.password(password).takeIf { register }
        repeatError = if (register && repeat != password) "Пароли не совпадают" else null
        if (login.isBlank()) loginError = "Введите логин"
        if (password.isEmpty()) passwordError = "Введите пароль"
        if (loginError != null || passwordError != null || repeatError != null) return
        if (serverUrl.isBlank()) { showServer = true; return }
        busy = true
        scope.launch {
            val result = if (register) container.repo.call { it.register(RegisterBody(login.trim(), password)) }
            else container.repo.call { it.login(LoginBody(login.trim(), password)) }
            busy = false
            when (result) {
                is ApiResult.Ok -> container.onAuthenticated(result.value.token, result.value.user)
                is ApiResult.Fail -> error = result.error.message
            }
        }
    }

    Column(
        Modifier.fillMaxSize().statusBarsPadding().navigationBarsPadding().imePadding()
            .verticalScroll(rememberScrollState()).padding(horizontal = 24.dp),
        horizontalAlignment = Alignment.CenterHorizontally,
    ) {
        Spacer(Modifier.height(56.dp))
        Text("SportCourts", style = AppType.logo, color = colors.text)
        Spacer(Modifier.height(6.dp))
        Text(
            if (register) "Найди идеальное место для игры" else "Рады возвращению",
            style = AppType.small, color = colors.textSecondary,
        )
        Spacer(Modifier.height(36.dp))
        Column(verticalArrangement = Arrangement.spacedBy(14.dp)) {
            if (notice != null) InlineError(notice)
            AppTextField(login, { login = it; loginError = null }, label = "Логин",
                placeholder = if (register) "Придумайте логин" else "Введите логин", error = loginError, maxLength = 32)
            AppTextField(password, { password = it; passwordError = null }, label = "Пароль", placeholder = "Не меньше 8 символов",
                password = true, error = passwordError, maxLength = 128,
                imeAction = if (register) ImeAction.Next else ImeAction.Done, onImeAction = { if (!register) submit() })
            if (register) {
                AppTextField(repeat, { repeat = it; repeatError = null }, label = "Повторите пароль", placeholder = "Ещё раз пароль",
                    password = true, error = repeatError, maxLength = 128, imeAction = ImeAction.Done, onImeAction = { submit() })
            }
            InlineError(error)
        }
        Spacer(Modifier.height(28.dp))
        PrimaryButton(if (register) "Создать аккаунт" else "Войти", { submit() }, loading = busy)
        Spacer(Modifier.height(8.dp))
        TextLink(
            if (register) "Уже есть аккаунт? Войти" else "Зарегистрироваться",
            { register = !register; error = null; loginError = null; passwordError = null; repeatError = null; container.clearNotice() },
        )
        Spacer(Modifier.height(24.dp))
        Text(
            if (serverUrl.isBlank()) "Адрес сервера не задан" else "Сервер: $serverUrl",
            style = AppType.caption, color = if (serverUrl.isBlank()) colors.danger else colors.textSecondary,
            textAlign = TextAlign.Center,
        )
        TextLink(if (serverUrl.isBlank()) "Указать адрес сервера" else "Изменить адрес сервера", { showServer = true })
        Spacer(Modifier.height(24.dp))
    }
    if (showServer) ServerAddressDialog(onDismiss = { showServer = false })
}

/** Смена адреса сервера без пересборки приложения (адрес Cloudflare Tunnel меняется при каждом запуске). */
@Composable
fun ServerAddressDialog(onDismiss: () -> Unit, onSaved: () -> Unit = {}) {
    val container = LocalContainer.current
    val scope = rememberCoroutineScope()
    val current by container.settings.collectAsState()
    var text by remember { mutableStateOf(current?.apiUrl.orEmpty()) }
    var busy by remember { mutableStateOf(false) }
    var error by remember { mutableStateOf<String?>(null) }
    var canForce by remember { mutableStateOf(false) }

    fun save(url: String) {
        scope.launch {
            container.setServerUrl(url)
            onSaved()
            onDismiss()
        }
    }

    AppDialog(onDismiss, "Адрес сервера", content = {
        Text(
            "Например: https://имя.trycloudflare.com. Адрес выдаёт тот, кто запускает сервер. " +
                "Если сервер или туннель перезапускали, адрес мог измениться.",
            style = AppType.small, color = colors.textSecondary,
        )
        AppTextField(text, { text = it; error = null; canForce = false }, placeholder = "https://…", singleLine = true,
            keyboardType = androidx.compose.ui.text.input.KeyboardType.Uri, imeAction = ImeAction.Done)
        InlineError(error)
    }) {
        Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
            PrimaryButton("Проверить и сохранить", {
                val url = normalizeServerUrl(text)
                if (url == null) {
                    error = "Некорректный адрес. Пример: https://имя.trycloudflare.com"
                } else {
                    busy = true
                    error = null
                    scope.launch {
                        val r = container.checkServer(url)
                        busy = false
                        when (r) {
                            is ApiResult.Ok -> save(url)
                            is ApiResult.Fail -> { error = r.error.message; canForce = true }
                        }
                    }
                }
            }, loading = busy)
            if (canForce) {
                SecondaryButton("Сохранить без проверки", { normalizeServerUrl(text)?.let { save(it) } })
            }
            SecondaryButton("Отмена", onDismiss)
        }
    }
}

/** Токен сохранён, но сервер недоступен: можно повторить попытку или поменять адрес. */
@Composable
fun UnreachableScreen(message: String) {
    val container = LocalContainer.current
    val scope = rememberCoroutineScope()
    var showServer by remember { mutableStateOf(false) }
    var busy by remember { mutableStateOf(false) }
    Column(
        Modifier.fillMaxSize().statusBarsPadding().navigationBarsPadding().padding(32.dp),
        horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.Center,
    ) {
        Text("SportCourts", style = AppType.logo, color = colors.text)
        Spacer(Modifier.height(24.dp))
        Text("Нет связи с сервером", style = AppType.bodyBold, color = colors.text)
        Spacer(Modifier.height(8.dp))
        Text(message, style = AppType.small, color = colors.textSecondary, textAlign = TextAlign.Center)
        Spacer(Modifier.height(24.dp))
        PrimaryButton("Повторить", { busy = true; scope.launch { container.retryStart(); busy = false } }, loading = busy)
        Spacer(Modifier.height(8.dp))
        SecondaryButton("Изменить адрес сервера", { showServer = true })
        Spacer(Modifier.height(8.dp))
        TextLink("Выйти из аккаунта", { container.logout() })
    }
    if (showServer) ServerAddressDialog(onDismiss = { showServer = false }, onSaved = { scope.launch { container.retryStart() } })
}

/** После сброса пароля администратором нужно задать новый пароль, прежде чем пользоваться приложением. */
@Composable
fun ForcePasswordScreen() {
    val container = LocalContainer.current
    val scope = rememberCoroutineScope()
    var current by remember { mutableStateOf("") }
    var newPassword by remember { mutableStateOf("") }
    var repeat by remember { mutableStateOf("") }
    var error by remember { mutableStateOf<String?>(null) }
    var busy by remember { mutableStateOf(false) }
    Column(
        Modifier.fillMaxSize().statusBarsPadding().navigationBarsPadding().imePadding()
            .verticalScroll(rememberScrollState()).padding(horizontal = 24.dp),
        horizontalAlignment = Alignment.CenterHorizontally,
    ) {
        Spacer(Modifier.height(56.dp))
        Text("Новый пароль", style = AppType.title, color = colors.text)
        Spacer(Modifier.height(6.dp))
        Text("Администратор выдал временный пароль. Задайте свой, чтобы продолжить.", style = AppType.small,
            color = colors.textSecondary, textAlign = TextAlign.Center)
        Spacer(Modifier.height(28.dp))
        Column(verticalArrangement = Arrangement.spacedBy(14.dp)) {
            AppTextField(current, { current = it }, label = "Временный пароль", password = true, maxLength = 128)
            AppTextField(newPassword, { newPassword = it }, label = "Новый пароль", placeholder = "Не меньше 8 символов", password = true, maxLength = 128)
            AppTextField(repeat, { repeat = it }, label = "Повторите новый пароль", password = true, maxLength = 128, imeAction = ImeAction.Done)
            InlineError(error)
        }
        Spacer(Modifier.height(24.dp))
        PrimaryButton("Сохранить пароль", {
            error = Validation.password(newPassword) ?: if (repeat != newPassword) "Пароли не совпадают" else null
            if (current.isEmpty()) error = "Введите временный пароль"
            if (error == null) {
                busy = true
                scope.launch {
                    val r = container.repo.call { it.changePassword(ChangePasswordBody(current, newPassword)) }
                    busy = false
                    when (r) {
                        is ApiResult.Ok -> container.updateMe(r.value)
                        is ApiResult.Fail -> error = r.error.message
                    }
                }
            }
        }, loading = busy)
        Spacer(Modifier.height(8.dp))
        TextLink("Выйти из аккаунта", { container.logout() })
    }
}
