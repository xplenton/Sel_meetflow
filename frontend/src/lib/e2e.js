/**
 * E2E Encryption Module for MeetFlow Chat
 * Uses ECDH for key exchange + AES-GCM for message encryption
 * All keys stay in the browser via Web Crypto API
 */

const DB_NAME = 'meetflow_e2e';
const DB_VERSION = 1;
const KEY_STORE = 'keys';

// ========== IndexedDB helpers for persistent key storage ==========

function openDB() {
  return new Promise((resolve, reject) => {
    const req = indexedDB.open(DB_NAME, DB_VERSION);
    req.onupgradeneeded = () => {
      const db = req.result;
      if (!db.objectStoreNames.contains(KEY_STORE)) {
        db.createObjectStore(KEY_STORE, { keyPath: 'id' });
      }
    };
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error);
  });
}

async function dbGet(id) {
  const db = await openDB();
  return new Promise((resolve, reject) => {
    const tx = db.transaction(KEY_STORE, 'readonly');
    const store = tx.objectStore(KEY_STORE);
    const req = store.get(id);
    req.onsuccess = () => resolve(req.result?.value || null);
    req.onerror = () => reject(req.error);
  });
}

async function dbPut(id, value) {
  const db = await openDB();
  return new Promise((resolve, reject) => {
    const tx = db.transaction(KEY_STORE, 'readwrite');
    const store = tx.objectStore(KEY_STORE);
    store.put({ id, value });
    tx.oncomplete = () => resolve();
    tx.onerror = () => reject(tx.error);
  });
}

// ========== Key Generation ==========

const ECDH_PARAMS = { name: 'ECDH', namedCurve: 'P-256' };
const AES_PARAMS = { name: 'AES-GCM', length: 256 };

/**
 * Generate an ECDH key pair and store the private key locally.
 * Returns the public key as a JWK string for server storage.
 */
export async function generateKeyPair(userId) {
  const keyPair = await crypto.subtle.generateKey(ECDH_PARAMS, true, ['deriveKey']);
  // Export private key as JWK and store in IndexedDB
  const privateJwk = await crypto.subtle.exportKey('jwk', keyPair.privateKey);
  await dbPut(`private_${userId}`, JSON.stringify(privateJwk));
  // Export public key as JWK string for server
  const publicJwk = await crypto.subtle.exportKey('jwk', keyPair.publicKey);
  return JSON.stringify(publicJwk);
}

/**
 * Check if a local private key exists for the user.
 */
export async function hasLocalKey(userId) {
  const stored = await dbGet(`private_${userId}`);
  return !!stored;
}

/**
 * Get or generate the user's public key JWK string.
 */
export async function getOrCreatePublicKey(userId) {
  const storedPrivate = await dbGet(`private_${userId}`);
  if (storedPrivate) {
    // Re-derive public from private
    const jwk = JSON.parse(storedPrivate);
    const privateKey = await crypto.subtle.importKey('jwk', jwk, ECDH_PARAMS, true, ['deriveKey']);
    // For ECDH, public key JWK is same as private JWK minus 'd' parameter
    const pubJwk = { ...jwk };
    delete pubJwk.d;
    pubJwk.key_ops = [];
    return JSON.stringify(pubJwk);
  }
  return await generateKeyPair(userId);
}

// ========== Shared Secret Derivation ==========

/**
 * Derive a shared AES-GCM key from our private key and their public key.
 * Results are cached in memory per session.
 */
const derivedKeyCache = {};

async function deriveSharedKey(myUserId, theirPublicKeyJwk) {
  const cacheKey = `${myUserId}_${theirPublicKeyJwk}`;
  if (derivedKeyCache[cacheKey]) return derivedKeyCache[cacheKey];

  // Import our private key
  const storedPrivate = await dbGet(`private_${myUserId}`);
  if (!storedPrivate) throw new Error('No private key found');
  const privateJwk = JSON.parse(storedPrivate);
  const privateKey = await crypto.subtle.importKey('jwk', privateJwk, ECDH_PARAMS, false, ['deriveKey']);

  // Import their public key
  const publicJwk = JSON.parse(theirPublicKeyJwk);
  const publicKey = await crypto.subtle.importKey('jwk', publicJwk, ECDH_PARAMS, false, []);

  // Derive shared AES key
  const sharedKey = await crypto.subtle.deriveKey(
    { name: 'ECDH', public: publicKey },
    privateKey,
    AES_PARAMS,
    false,
    ['encrypt', 'decrypt']
  );

  derivedKeyCache[cacheKey] = sharedKey;
  return sharedKey;
}

// ========== Group Key (symmetric, shared via public keys) ==========

/**
 * For group chats, generate a random AES key and store per conversation.
 */
export async function getOrCreateGroupKey(conversationId) {
  const stored = await dbGet(`group_${conversationId}`);
  if (stored) {
    const jwk = JSON.parse(stored);
    return await crypto.subtle.importKey('jwk', jwk, AES_PARAMS, true, ['encrypt', 'decrypt']);
  }
  const key = await crypto.subtle.generateKey(AES_PARAMS, true, ['encrypt', 'decrypt']);
  const jwk = await crypto.subtle.exportKey('jwk', key);
  await dbPut(`group_${conversationId}`, JSON.stringify(jwk));
  return key;
}

/**
 * Import a group key received from another member.
 */
export async function importGroupKey(conversationId, keyJwkString) {
  const jwk = JSON.parse(keyJwkString);
  await dbPut(`group_${conversationId}`, JSON.stringify(jwk));
  return await crypto.subtle.importKey('jwk', jwk, AES_PARAMS, true, ['encrypt', 'decrypt']);
}

/**
 * Export the group key as JWK string (for sharing with new members).
 */
export async function exportGroupKey(conversationId) {
  const stored = await dbGet(`group_${conversationId}`);
  return stored || null;
}

// ========== Encrypt / Decrypt ==========

/**
 * Encrypt a plaintext string with an AES-GCM key.
 * Returns base64 string: iv (12 bytes) + ciphertext.
 */
export async function encryptMessage(plaintext, aesKey) {
  const iv = crypto.getRandomValues(new Uint8Array(12));
  const encoded = new TextEncoder().encode(plaintext);
  const ciphertext = await crypto.subtle.encrypt({ name: 'AES-GCM', iv }, aesKey, encoded);
  // Combine IV + ciphertext
  const combined = new Uint8Array(iv.length + ciphertext.byteLength);
  combined.set(iv, 0);
  combined.set(new Uint8Array(ciphertext), iv.length);
  return btoa(String.fromCharCode(...combined));
}

/**
 * Decrypt a base64 string (iv + ciphertext) with an AES-GCM key.
 * Returns plaintext string, or null on failure.
 */
export async function decryptMessage(base64Data, aesKey) {
  try {
    const raw = Uint8Array.from(atob(base64Data), c => c.charCodeAt(0));
    const iv = raw.slice(0, 12);
    const ciphertext = raw.slice(12);
    const decrypted = await crypto.subtle.decrypt({ name: 'AES-GCM', iv }, aesKey, ciphertext);
    return new TextDecoder().decode(decrypted);
  } catch {
    return null; // Decryption failed (wrong key, corrupted data, etc.)
  }
}

// ========== High-level helpers for Chat integration ==========

/**
 * Encrypt message content for a conversation.
 * For direct chats: uses ECDH-derived shared key.
 * For group chats: uses a symmetric group key.
 */
export async function encryptForConversation(myUserId, conversation, plaintext, peerPublicKeyJwk) {
  if (conversation.type === 'direct' && peerPublicKeyJwk) {
    const sharedKey = await deriveSharedKey(myUserId, peerPublicKeyJwk);
    return await encryptMessage(plaintext, sharedKey);
  }
  // Group: use group key
  const groupKey = await getOrCreateGroupKey(conversation.conversation_id);
  return await encryptMessage(plaintext, groupKey);
}

/**
 * Decrypt message content from a conversation.
 */
export async function decryptForConversation(myUserId, conversation, ciphertext, peerPublicKeyJwk) {
  if (!ciphertext) return '';
  // Check if it looks like encrypted content (base64)
  if (!/^[A-Za-z0-9+/]+=*$/.test(ciphertext) || ciphertext.length < 20) {
    return ciphertext; // Not encrypted, return as-is
  }
  try {
    if (conversation.type === 'direct' && peerPublicKeyJwk) {
      const sharedKey = await deriveSharedKey(myUserId, peerPublicKeyJwk);
      const result = await decryptMessage(ciphertext, sharedKey);
      return result ?? ciphertext;
    }
    // Group: use group key
    const groupKey = await getOrCreateGroupKey(conversation.conversation_id);
    const result = await decryptMessage(ciphertext, groupKey);
    return result ?? ciphertext;
  } catch {
    return ciphertext; // Fallback: show raw content
  }
}

/**
 * Check if Web Crypto API is available.
 */
export function isE2ESupported() {
  return typeof crypto !== 'undefined' && typeof crypto.subtle !== 'undefined';
}
