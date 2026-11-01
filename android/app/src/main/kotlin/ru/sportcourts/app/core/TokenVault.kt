package ru.sportcourts.app.core

import android.content.Context
import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyProperties
import android.util.Base64
import java.security.KeyStore
import javax.crypto.Cipher
import javax.crypto.KeyGenerator
import javax.crypto.SecretKey
import javax.crypto.spec.GCMParameterSpec

/**
 * Хранилище токена сессии. Токен шифруется ключом AES-GCM из Android Keystore,
 * шифртекст лежит в приватных SharedPreferences. Если Keystore недоступен (бывает на эмуляторах),
 * токен живёт только в памяти — после перезапуска придётся войти заново, но пароль нигде не хранится.
 */
class TokenVault(context: Context) {
    private val prefs = context.getSharedPreferences("secure_session", Context.MODE_PRIVATE)
    @Volatile private var memoryToken: String? = null

    private fun key(): SecretKey {
        val ks = KeyStore.getInstance("AndroidKeyStore").apply { load(null) }
        (ks.getKey(ALIAS, null) as? SecretKey)?.let { return it }
        val gen = KeyGenerator.getInstance(KeyProperties.KEY_ALGORITHM_AES, "AndroidKeyStore")
        gen.init(
            KeyGenParameterSpec.Builder(ALIAS, KeyProperties.PURPOSE_ENCRYPT or KeyProperties.PURPOSE_DECRYPT)
                .setBlockModes(KeyProperties.BLOCK_MODE_GCM)
                .setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE)
                .setKeySize(256)
                .build()
        )
        return gen.generateKey()
    }

    fun save(token: String) {
        memoryToken = token
        try {
            val cipher = Cipher.getInstance(TRANSFORMATION)
            cipher.init(Cipher.ENCRYPT_MODE, key())
            val encrypted = cipher.doFinal(token.toByteArray(Charsets.UTF_8))
            val packed = Base64.encodeToString(cipher.iv, Base64.NO_WRAP) + ":" + Base64.encodeToString(encrypted, Base64.NO_WRAP)
            prefs.edit().putString(PREF_KEY, packed).apply()
        } catch (e: Exception) {
            prefs.edit().remove(PREF_KEY).apply()
        }
    }

    fun load(): String? {
        memoryToken?.let { return it }
        val packed = prefs.getString(PREF_KEY, null) ?: return null
        return try {
            val (iv, data) = packed.split(":", limit = 2)
            val cipher = Cipher.getInstance(TRANSFORMATION)
            cipher.init(Cipher.DECRYPT_MODE, key(), GCMParameterSpec(128, Base64.decode(iv, Base64.NO_WRAP)))
            String(cipher.doFinal(Base64.decode(data, Base64.NO_WRAP)), Charsets.UTF_8).also { memoryToken = it }
        } catch (e: Exception) {
            clear()
            null
        }
    }

    fun clear() {
        memoryToken = null
        prefs.edit().remove(PREF_KEY).apply()
    }

    private companion object {
        const val ALIAS = "sportcourts_session_key"
        const val PREF_KEY = "token"
        const val TRANSFORMATION = "AES/GCM/NoPadding"
    }
}
