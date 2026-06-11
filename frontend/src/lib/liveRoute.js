/**
 * Live-meeting route resolver (iter 140).
 *
 * Since iter 140 there is exactly ONE meeting transport — LiveKit SFU —
 * embedded inside the canonical `/meetings/:id/live` page. The helper
 * remains to keep callers abstracted from the URL choice in case we ever
 * split the route again.
 *
 * @param {string} meetingId
 * @returns {Promise<string>} absolute path beginning with `/meetings/`
 */
export async function resolveLiveRoute(meetingId /* , _knownHeadcount */) {
  return `/meetings/${meetingId}/live`;
}
