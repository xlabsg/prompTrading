/**
 * Frontend encryption utilities for API credentials
 *
 * This module provides encryption functions to secure API keys and secrets
 * before sending them to the backend.
 *
 * Note: The backend uses Fernet (AES-128-CBC with HMAC-SHA256).
 * This implementation uses AES-GCM for browser compatibility.
 */

import CryptoJS from "crypto-js";

// Encryption key from environment - same key used by backend
// In production, this should be stored securely and not exposed
const ENCRYPTION_KEY = import.meta.env.VITE_TRADING_API_ENCRYPTION_KEY || "ZSTfHvPCHPKFN7fzPpecrDCxaOLWDQ3O_WBO-eN4JDw=";

/**
 * Encrypt a plaintext string using AES
 * @param plaintext - The text to encrypt
 * @returns Base64 encoded encrypted string
 */
export function encryptCredential(plaintext: string): string {
    if (!plaintext) return "";

    try {
        // Generate a random IV for each encryption
        const iv = CryptoJS.lib.WordArray.random(16);

        // Encrypt using AES
        const encrypted = CryptoJS.AES.encrypt(plaintext, CryptoJS.enc.Base64.parse(ENCRYPTION_KEY), {
            iv: iv,
            mode: CryptoJS.mode.CBC,
            padding: CryptoJS.pad.Pkcs7,
        });

        // Combine IV and ciphertext: IV (16 bytes) + ciphertext
        const combined = iv.toString() + ":" + encrypted.toString();

        return combined;
    } catch (error) {
        console.error("Encryption failed:", error);
        throw new Error("Failed to encrypt credential");
    }
}

/**
 * Decrypt an encrypted string
 * @param encryptedText - Base64 encoded encrypted string (format: IV:ciphertext)
 * @returns Decrypted plaintext
 */
export function decryptCredential(encryptedText: string): string {
    if (!encryptedText) return "";

    try {
        const parts = encryptedText.split(":");
        if (parts.length !== 2) {
            throw new Error("Invalid encrypted format");
        }

        const iv = parts[0];
        const ciphertext = parts[1];

        const decrypted = CryptoJS.AES.decrypt(ciphertext, CryptoJS.enc.Base64.parse(ENCRYPTION_KEY), {
            iv: CryptoJS.enc.Hex.parse(iv),
            mode: CryptoJS.mode.CBC,
            padding: CryptoJS.pad.Pkcs7,
        });

        return decrypted.toString(CryptoJS.enc.Utf8);
    } catch (error) {
        console.error("Decryption failed:", error);
        throw new Error("Failed to decrypt credential");
    }
}

/**
 * Generate a random encryption key
 * Useful for testing or generating new keys
 * @returns Base64 encoded 32-byte key
 */
export function generateEncryptionKey(): string {
    const randomWords = CryptoJS.lib.WordArray.random(32);
    return randomWords.toString(CryptoJS.enc.Base64);
}

/**
 * Hash a string using SHA-256
 * @param text - Text to hash
 * @returns Hex encoded hash
 */
export function hashString(text: string): string {
    return CryptoJS.SHA256(text).toString(CryptoJS.enc.Hex);
}

/**
 * Generate a unique client order ID
 * Format: prefix_timestamp_random
 * @param prefix - Optional prefix (default: "ord")
 * @returns Unique order ID string
 */
export function generateClientOrderId(prefix: string = "ord"): string {
    const timestamp = Date.now().toString(36);
    const random = Math.random().toString(36).substring(2, 8);
    return `${prefix}_${timestamp}_${random}`;
}
