/**
 * Unit tests for `useBookingDialog` — the hook extracted from BookingDialog
 * in iter 302. Guards against regressions in conflict detection, quick-date
 * shortcuts, suggestion acceptance and the three submit paths
 * (single / series / combo).
 *
 * Network (`../../../lib/api`) and toasts (`sonner`) are mocked so tests
 * stay fast and offline. Timers are faked because the conflict check is
 * debounced by 400ms.
 */
import { renderHook, act, waitFor } from '@testing-library/react';
import useBookingDialog from './useBookingDialog';
import api from '../../../lib/api';

jest.mock('../../../lib/api', () => ({
  __esModule: true,
  default: {
    get: jest.fn(),
    post: jest.fn(),
  },
}));

jest.mock('sonner', () => ({
  toast: { success: jest.fn(), error: jest.fn(), info: jest.fn() },
}));

const baseResource = {
  resource_id: 'res_room_1',
  name: 'Raum 1',
  type: 'room',
  is_splitable: false,
  requires_approval: false,
  allow_catering: false,
  children: [],
};

function setupGetMocks({ catering = [], costCenters = [], accounts = [], bookable = [] } = {}) {
  // initial-load effect fires four GETs (catering only if allow_catering)
  api.get.mockImplementation((url) => {
    if (url === '/catering-items') return Promise.resolve({ data: catering });
    if (url === '/cost-centers') return Promise.resolve({ data: costCenters });
    if (url === '/accounts') return Promise.resolve({ data: accounts });
    if (url === '/users/bookable-for') return Promise.resolve({ data: bookable });
    return Promise.resolve({ data: [] });
  });
}

beforeEach(() => {
  jest.clearAllMocks();
  jest.useFakeTimers();
});

afterEach(() => {
  jest.useRealTimers();
});

describe('useBookingDialog — initial state', () => {
  test('exposes sane defaults and pre-selects the resource as target', async () => {
    setupGetMocks();
    api.post.mockResolvedValue({ data: { conflicts: [] } });
    const onClose = jest.fn();
    const { result } = renderHook(() => useBookingDialog(baseResource, onClose));

    // Debounced conflict-check is already scheduled on mount → checking=true.
    expect(result.current.target).toBe('res_room_1');
    expect(result.current.title).toBe('');
    expect(result.current.conflicts).toEqual([]);
    expect(result.current.suggestions).toEqual([]);
    expect(result.current.submitting).toBe(false);
    expect(result.current.seriesEnabled).toBe(false);
    expect(result.current.disabledReason).toBe('Titel fehlt');

    // Flush the debounce so the test ends in a quiet state.
    await act(async () => { jest.advanceTimersByTime(500); });
    await waitFor(() => expect(result.current.checking).toBe(false));
  });

  test('builds the splitable target list from resource.children', () => {
    setupGetMocks();
    const splitable = {
      ...baseResource,
      is_splitable: true,
      children: [
        { resource_id: 'res_room_1_a', sub_id: 'A' },
        { resource_id: 'res_room_1_b', sub_id: 'B' },
      ],
    };
    const { result } = renderHook(() => useBookingDialog(splitable, jest.fn()));
    const ids = result.current.targets.map((t) => t.id);
    expect(ids).toEqual(['res_room_1', 'res_room_1_a', 'res_room_1_b']);
  });
});

describe('useBookingDialog — conflict detection', () => {
  test('POSTs check-conflicts and clears suggestions when slot is free', async () => {
    setupGetMocks();
    api.post.mockResolvedValueOnce({ data: { conflicts: [] } });

    const { result } = renderHook(() => useBookingDialog(baseResource, jest.fn()));

    // initial debounce fires once on mount with default start/end
    await act(async () => { jest.advanceTimersByTime(500); });
    await waitFor(() => expect(result.current.checking).toBe(false));

    expect(api.post).toHaveBeenCalledWith(
      '/resources/res_room_1/check-conflicts',
      expect.objectContaining({ start_at: expect.any(String), end_at: expect.any(String) }),
    );
    expect(result.current.conflicts).toEqual([]);
    expect(result.current.suggestions).toEqual([]);
  });

  test('fetches suggest-slots after a conflict and stores them', async () => {
    setupGetMocks();
    api.post
      .mockResolvedValueOnce({ data: { conflicts: [{ title: 'Belegt', start_at: 'x', end_at: 'y' }] } })
      .mockResolvedValueOnce({ data: { suggestions: [{ start_at: '2026-06-01T10:00:00Z', end_at: '2026-06-01T11:00:00Z' }] } });

    const { result } = renderHook(() => useBookingDialog(baseResource, jest.fn()));
    await act(async () => { jest.advanceTimersByTime(500); });
    await waitFor(() => expect(result.current.checking).toBe(false));

    expect(api.post).toHaveBeenNthCalledWith(
      2,
      '/resources/res_room_1/suggest-slots',
      expect.objectContaining({ count: 3, duration_min: expect.any(Number) }),
    );
    expect(result.current.conflicts).toHaveLength(1);
    expect(result.current.suggestions).toHaveLength(1);
  });
});

describe('useBookingDialog — helpers', () => {
  test('setDuration adjusts end relative to start', async () => {
    setupGetMocks();
    api.post.mockResolvedValue({ data: { conflicts: [] } });
    const { result } = renderHook(() => useBookingDialog(baseResource, jest.fn()));

    act(() => { result.current.setStart('2026-06-01T09:00'); });
    act(() => { result.current.setDuration(90); });

    // 09:00 + 90 min = 10:30
    expect(result.current.end).toBe('2026-06-01T10:30');
  });

  test('acceptSuggestion copies the slot into start/end (local time)', async () => {
    setupGetMocks();
    api.post.mockResolvedValue({ data: { conflicts: [] } });
    const { result } = renderHook(() => useBookingDialog(baseResource, jest.fn()));

    act(() => {
      result.current.acceptSuggestion({
        start_at: '2026-06-01T08:00:00Z',
        end_at: '2026-06-01T09:00:00Z',
      });
    });

    // toLocal renders local time — we don't assert the timezone-dependent value,
    // just that both fields are now non-empty strings of the expected shape.
    expect(result.current.start).toMatch(/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$/);
    expect(result.current.end).toMatch(/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$/);
  });
});

describe('useBookingDialog — submit paths', () => {
  test('refuses to submit while title is empty (disabledReason)', async () => {
    setupGetMocks();
    api.post.mockResolvedValue({ data: { conflicts: [] } });
    const onClose = jest.fn();
    const { result } = renderHook(() => useBookingDialog(baseResource, onClose));

    await act(async () => { jest.advanceTimersByTime(500); });
    await waitFor(() => expect(result.current.checking).toBe(false));

    // Snapshot post-call count before submit attempt
    const postsBefore = api.post.mock.calls.length;
    await act(async () => { await result.current.submit(); });

    expect(result.current.disabledReason).toBe('Titel fehlt');
    expect(api.post.mock.calls.length).toBe(postsBefore); // no extra POST
    expect(onClose).not.toHaveBeenCalled();
  });

  test('single booking → POST /resource-bookings with the right payload', async () => {
    setupGetMocks();
    api.post
      .mockResolvedValueOnce({ data: { conflicts: [] } })   // initial conflict check
      .mockResolvedValueOnce({ data: { booking_id: 'bk1' } }); // submit

    const onClose = jest.fn();
    const { result } = renderHook(() => useBookingDialog(baseResource, onClose));

    await act(async () => { jest.advanceTimersByTime(500); });
    await waitFor(() => expect(result.current.checking).toBe(false));

    act(() => { result.current.setTitle('Sprint Planning'); });
    await act(async () => { await result.current.submit(); });

    expect(api.post).toHaveBeenLastCalledWith(
      '/resource-bookings',
      expect.objectContaining({
        resource_id: 'res_room_1',
        title: 'Sprint Planning',
        start_at: expect.any(String),
        end_at: expect.any(String),
      }),
    );
    expect(onClose).toHaveBeenCalledWith(true);
  });

  test('series booking → POST /resource-bookings/series', async () => {
    setupGetMocks();
    api.post
      .mockResolvedValueOnce({ data: { conflicts: [] } })
      .mockResolvedValueOnce({ data: { created: ['a', 'b'], skipped: [] } });

    const onClose = jest.fn();
    const { result } = renderHook(() => useBookingDialog(baseResource, onClose));

    await act(async () => { jest.advanceTimersByTime(500); });
    await waitFor(() => expect(result.current.checking).toBe(false));

    act(() => {
      result.current.setTitle('Wochenrunde');
      result.current.setSeriesEnabled(true);
      result.current.setSeriesOccurrences(2);
      result.current.setSeriesRecurrence('weekly');
    });
    await act(async () => { await result.current.submit(); });

    expect(api.post).toHaveBeenLastCalledWith(
      '/resource-bookings/series',
      expect.objectContaining({
        resource_id: 'res_room_1',
        title: 'Wochenrunde',
        recurrence: 'weekly',
        occurrences: 2,
      }),
    );
    expect(onClose).toHaveBeenCalledWith(true);
  });

  test('combo booking → POST /resource-bookings/combo when ≥2 sub-ids selected on a splitable', async () => {
    setupGetMocks();
    api.post
      .mockResolvedValueOnce({ data: { conflicts: [] } })
      .mockResolvedValueOnce({ data: { booking_id: 'combo1' } });

    const splitable = {
      ...baseResource,
      is_splitable: true,
      children: [
        { resource_id: 'res_room_1_a', sub_id: 'A' },
        { resource_id: 'res_room_1_b', sub_id: 'B' },
      ],
    };
    const onClose = jest.fn();
    const { result } = renderHook(() => useBookingDialog(splitable, onClose));

    await act(async () => { jest.advanceTimersByTime(500); });
    await waitFor(() => expect(result.current.checking).toBe(false));

    act(() => {
      result.current.setTitle('Kombi');
      result.current.setComboSubs(['A', 'B']);
    });
    await act(async () => { await result.current.submit(); });

    expect(api.post).toHaveBeenLastCalledWith(
      '/resource-bookings/combo',
      expect.objectContaining({
        parent_resource_id: 'res_room_1',
        sub_ids: ['A', 'B'],
        title: 'Kombi',
      }),
    );
    expect(onClose).toHaveBeenCalledWith(true);
  });

  test('on 409 conflict the conflicts list is updated and onClose is NOT called', async () => {
    setupGetMocks();
    api.post
      .mockResolvedValueOnce({ data: { conflicts: [] } }) // initial check
      .mockRejectedValueOnce({                            // submit fails with 409
        response: { status: 409, data: { detail: { conflicts: [{ title: 'Belegt' }] } } },
      });

    const onClose = jest.fn();
    const { result } = renderHook(() => useBookingDialog(baseResource, onClose));

    await act(async () => { jest.advanceTimersByTime(500); });
    await waitFor(() => expect(result.current.checking).toBe(false));

    act(() => { result.current.setTitle('Wird belegt'); });
    await act(async () => { await result.current.submit(); });

    expect(result.current.conflicts).toEqual([{ title: 'Belegt' }]);
    expect(onClose).not.toHaveBeenCalled();
  });
});
