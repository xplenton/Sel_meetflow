/**
 * Unit tests for `useNewsPostDetail` — the custom hook that bundles
 * comments/questions/sentiment state out of NewsPage.
 *
 * These tests document the public surface of the hook and guard against
 * regressions during future refactors of NewsPage.
 *
 * The hook talks to `../lib/api` (axios wrapper). We mock that module so
 * tests stay fast & offline. Each test asserts the local state in addition
 * to the API call shape.
 */
import { renderHook, act } from '@testing-library/react';
import useNewsPostDetail from './useNewsPostDetail';
import api from '../lib/api';

jest.mock('../lib/api', () => ({
  __esModule: true,
  default: {
    get: jest.fn(),
    post: jest.fn(),
    delete: jest.fn(),
  },
}));

beforeEach(() => {
  jest.clearAllMocks();
});

describe('useNewsPostDetail', () => {
  test('returns the expected initial state', () => {
    const { result } = renderHook(() => useNewsPostDetail());
    expect(result.current.comments).toEqual([]);
    expect(result.current.questions).toEqual([]);
    expect(result.current.sentiment).toBeNull();
    expect(result.current.commentText).toBe('');
    expect(result.current.commentAttachments).toEqual([]);
    expect(result.current.replyingTo).toBeNull();
    expect(result.current.questionText).toBe('');
  });

  test('load() fetches comments + questions and stores them in state', async () => {
    api.get
      .mockResolvedValueOnce({ data: [{ comment_id: 'c1', content: 'Hello' }] })   // /comments
      .mockResolvedValueOnce({ data: [{ question_id: 'q1', text: 'Why?' }] });      // /questions

    const { result } = renderHook(() => useNewsPostDetail());

    await act(async () => {
      await result.current.load('post-1');
    });

    expect(api.get).toHaveBeenCalledWith('/news/posts/post-1/comments');
    expect(api.get).toHaveBeenCalledWith('/news/posts/post-1/questions');
    expect(result.current.comments).toEqual([{ comment_id: 'c1', content: 'Hello' }]);
    expect(result.current.questions).toEqual([{ question_id: 'q1', text: 'Why?' }]);
  });

  test('load() resets draft fields and sentiment', async () => {
    api.get.mockResolvedValue({ data: [] });
    const { result } = renderHook(() => useNewsPostDetail());

    act(() => {
      result.current.setCommentText('draft');
      result.current.setQuestionText('q draft');
      result.current.setSentiment({ score: 0.5 });
      result.current.setReplyingTo({ comment_id: 'c1' });
    });
    expect(result.current.commentText).toBe('draft');

    await act(async () => {
      await result.current.load('post-2');
    });

    expect(result.current.commentText).toBe('');
    expect(result.current.questionText).toBe('');
    expect(result.current.sentiment).toBeNull();
    expect(result.current.replyingTo).toBeNull();
  });

  test('addComment() POSTs with content + clears the draft + appends locally', async () => {
    const newComment = { comment_id: 'cX', content: 'Hi there' };
    api.post.mockResolvedValueOnce({ data: newComment });

    const { result } = renderHook(() => useNewsPostDetail());

    act(() => result.current.setCommentText('Hi there'));

    let returned;
    await act(async () => {
      returned = await result.current.addComment('post-1');
    });

    expect(api.post).toHaveBeenCalledWith('/news/posts/post-1/comments', { content: 'Hi there' });
    expect(returned).toEqual(newComment);
    expect(result.current.comments).toContainEqual(newComment);
    expect(result.current.commentText).toBe('');
    expect(result.current.commentAttachments).toEqual([]);
    expect(result.current.replyingTo).toBeNull();
  });

  test('addComment() includes parent_id when replyingTo is set', async () => {
    api.post.mockResolvedValueOnce({ data: { comment_id: 'r1', content: 'reply' } });
    const { result } = renderHook(() => useNewsPostDetail());

    act(() => {
      result.current.setCommentText('reply');
      result.current.setReplyingTo({ comment_id: 'parent-c' });
    });

    await act(async () => {
      await result.current.addComment('post-1');
    });

    expect(api.post).toHaveBeenCalledWith('/news/posts/post-1/comments', {
      content: 'reply',
      parent_id: 'parent-c',
    });
  });

  test('addComment() short-circuits when both text and attachments are empty', async () => {
    const { result } = renderHook(() => useNewsPostDetail());
    let returned;
    await act(async () => {
      returned = await result.current.addComment('post-1');
    });
    expect(returned).toBeNull();
    expect(api.post).not.toHaveBeenCalled();
  });

  test('addComment() includes attachment ids when provided', async () => {
    api.post.mockResolvedValueOnce({ data: { comment_id: 'c2', content: '' } });
    const { result } = renderHook(() => useNewsPostDetail());

    act(() => {
      result.current.setCommentAttachments([
        { attachment_id: 'a1' }, { attachment_id: 'a2' },
      ]);
    });

    await act(async () => {
      await result.current.addComment('post-1');
    });

    expect(api.post).toHaveBeenCalledWith('/news/posts/post-1/comments', {
      content: '',
      attachments: ['a1', 'a2'],
    });
  });

  test('deleteComment() removes the comment from local state', async () => {
    api.get
      .mockResolvedValueOnce({ data: [{ comment_id: 'c1' }, { comment_id: 'c2' }] })
      .mockResolvedValueOnce({ data: [] });
    api.delete.mockResolvedValueOnce({});

    const { result } = renderHook(() => useNewsPostDetail());

    await act(async () => { await result.current.load('post-1'); });
    expect(result.current.comments).toHaveLength(2);

    await act(async () => { await result.current.deleteComment('c1'); });

    expect(api.delete).toHaveBeenCalledWith('/news/comments/c1');
    expect(result.current.comments).toEqual([{ comment_id: 'c2' }]);
  });

  test('toggleReaction() POSTs and re-fetches the post', async () => {
    api.post.mockResolvedValueOnce({ data: {} });
    api.get.mockResolvedValueOnce({ data: { post_id: 'p1', user_reaction: 'like' } });

    const { result } = renderHook(() => useNewsPostDetail());

    let fresh;
    await act(async () => {
      fresh = await result.current.toggleReaction('p1', 'like');
    });

    expect(api.post).toHaveBeenCalledWith('/news/posts/p1/reactions', { reaction_type: 'like' });
    expect(api.get).toHaveBeenCalledWith('/news/posts/p1');
    expect(fresh).toEqual({ post_id: 'p1', user_reaction: 'like' });
  });

  test('askQuestion() POSTs and clears the draft', async () => {
    const newQ = { question_id: 'q9', text: 'Test?' };
    api.post.mockResolvedValueOnce({ data: newQ });

    const { result } = renderHook(() => useNewsPostDetail());
    act(() => result.current.setQuestionText('Test?'));

    let returned;
    await act(async () => {
      returned = await result.current.askQuestion('post-1');
    });

    expect(api.post).toHaveBeenCalledWith('/news/posts/post-1/questions', { text: 'Test?' });
    expect(returned).toEqual(newQ);
    expect(result.current.questions).toContainEqual(newQ);
    expect(result.current.questionText).toBe('');
  });

  test('askQuestion() with empty text short-circuits', async () => {
    const { result } = renderHook(() => useNewsPostDetail());
    let returned;
    await act(async () => {
      returned = await result.current.askQuestion('post-1');
    });
    expect(returned).toBeNull();
    expect(api.post).not.toHaveBeenCalled();
  });

  test('upvoteQuestion() merges upvote_count + user_upvoted into the matching question', async () => {
    api.get.mockResolvedValueOnce({ data: [] }).mockResolvedValueOnce({
      data: [{ question_id: 'q1', upvote_count: 0, user_upvoted: false }],
    });
    api.post.mockResolvedValueOnce({ data: { upvote_count: 1, user_upvoted: true } });

    const { result } = renderHook(() => useNewsPostDetail());
    await act(async () => { await result.current.load('post-1'); });
    expect(result.current.questions).toHaveLength(1);

    await act(async () => { await result.current.upvoteQuestion('q1'); });

    expect(api.post).toHaveBeenCalledWith('/news/questions/q1/upvote');
    expect(result.current.questions[0]).toMatchObject({
      question_id: 'q1', upvote_count: 1, user_upvoted: true,
    });
  });

  test('runSentiment() stores the sentiment result in state', async () => {
    const sentimentResult = { positive: 0.8, neutral: 0.1, negative: 0.1 };
    api.get.mockResolvedValueOnce({ data: sentimentResult });

    const { result } = renderHook(() => useNewsPostDetail());

    let returned;
    await act(async () => {
      returned = await result.current.runSentiment('post-1');
    });

    expect(api.get).toHaveBeenCalledWith('/news/posts/post-1/sentiment');
    expect(returned).toEqual(sentimentResult);
    expect(result.current.sentiment).toEqual(sentimentResult);
  });

  test('reset() clears everything', async () => {
    api.get.mockResolvedValueOnce({ data: [{ comment_id: 'c1' }] })
      .mockResolvedValueOnce({ data: [{ question_id: 'q1' }] });

    const { result } = renderHook(() => useNewsPostDetail());
    await act(async () => { await result.current.load('post-1'); });
    act(() => { result.current.setCommentText('foo'); });
    expect(result.current.comments).toHaveLength(1);

    act(() => { result.current.reset(); });

    expect(result.current.comments).toEqual([]);
    expect(result.current.questions).toEqual([]);
    expect(result.current.commentText).toBe('');
    expect(result.current.sentiment).toBeNull();
  });
});
