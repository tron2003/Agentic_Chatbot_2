/**
 * Chat ID Generator utility
 * Generates random, unique chat IDs for new conversations
 */

/**
 * Generate a random unique chat ID
 * Format: chat_[uuid]_[timestamp]
 */
export const generateChatId = (): string => {
  const uuid = generateUUID();
  const timestamp = Date.now();
  return `chat_${uuid}_${timestamp}`;
};

/**
 * Generate a UUID v4
 * Based on RFC 4122
 */
export const generateUUID = (): string => {
  return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, function (c) {
    const r = (Math.random() * 16) | 0;
    const v = c === 'x' ? r : (r & 0x3) | 0x8;
    return v.toString(16);
  });
};

/**
 * Format chat ID for display (show last 8 chars of UUID)
 */
export const formatChatIdForDisplay = (chatId: string): string => {
  const uuidPart = chatId.split('_')[1];
  if (uuidPart) {
    return uuidPart.slice(-8).toUpperCase();
  }
  return chatId.slice(-8).toUpperCase();
};

/**
 * Get display name for chat based on first message
 */
export const getChatDisplayName = (
  firstMessage: string,
  maxLength: number = 30
): string => {
  if (!firstMessage) return 'New Chat';
  return firstMessage.slice(0, maxLength).trim() + (firstMessage.length > maxLength ? '...' : '');
};

/**
 * Format date for chat history display
 */
export const formatChatDate = (date: Date | string): string => {
  const d = typeof date === 'string' ? new Date(date) : date;
  const now = new Date();
  const diffMs = now.getTime() - d.getTime();
  const diffMins = Math.floor(diffMs / 60000);
  const diffHours = Math.floor(diffMs / 3600000);
  const diffDays = Math.floor(diffMs / 86400000);

  if (diffMins < 1) return 'Just now';
  if (diffMins < 60) return `${diffMins}m ago`;
  if (diffHours < 24) return `${diffHours}h ago`;
  if (diffDays === 1) return 'Yesterday';
  if (diffDays < 7) return `${diffDays}d ago`;

  return d.toLocaleDateString([], { month: 'short', day: 'numeric' });
};
