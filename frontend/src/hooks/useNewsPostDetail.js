import { useState, useCallback, useEffect } from 'react';
import api from '../lib/api';

/**
 * useNewsPostDetail — extracts the comments / questions / sentiment state
 * (plus their handlers) out of NewsPage during the iter 218 refactor.
 *
 * The detail view of a news post needs a fair amount of co-located state
 * (replies, draft text, attachments, Q&A draft, sentiment result, …). The
 * page used to inline 10+ useState hooks for this. Bundling them into a
 * single hook keeps the page focused on the feed-list concerns and makes
 * the detail logic re-usable & testable in isolation.
 *
 * Returns:
 *   - comments, replyingTo, commentText, commentAttachments + setters
 *   - questions, questionText + setter
 *   - sentiment + setter
 *   - load(postId) — fetches comments & questions for a post and resets
 *     transient draft fields and sentiment.
 *   - reset() — clears everything (used on dialog close).
 *   - addComment(postId, parentId?) — POSTs the current draft to the API,
 *     appends the new comment locally and clears the draft + reply target.
 *   - deleteComment(commentId)
 *   - toggleReaction(postId, type) — re-fetches the post to refresh counts.
 *   - askQuestion(postId)
 *   - answerQuestion(questionId, postId)
 *   - upvoteQuestion(questionId)
 *   - runSentiment(postId)
 */
export default function useNewsPostDetail() {
  const [comments, setComments] = useState([]);
  const [commentText, setCommentText] = useState('');
  const [commentAttachments, setCommentAttachments] = useState([]);
  const [replyingTo, setReplyingTo] = useState(null);
  const [questions, setQuestions] = useState([]);
  const [questionText, setQuestionText] = useState('');
  const [sentiment, setSentiment] = useState(null);

  const reset = useCallback(() => {
    setComments([]);
    setCommentText('');
    setCommentAttachments([]);
    setReplyingTo(null);
    setQuestions([]);
    setQuestionText('');
    setSentiment(null);
  }, []);

  const load = useCallback(async (postId) => {
    setSentiment(null);
    setReplyingTo(null);
    setCommentText('');
    setCommentAttachments([]);
    setQuestionText('');
    try {
      const [cRes, qRes] = await Promise.all([
        api.get(`/news/posts/${postId}/comments`),
        api.get(`/news/posts/${postId}/questions`),
      ]);
      setComments(cRes.data || []);
      setQuestions(qRes.data || []);
    } catch {
      setComments([]);
      setQuestions([]);
    }
  }, []);

  const addComment = useCallback(async (postId) => {
    if (!commentText.trim() && commentAttachments.length === 0) return null;
    const payload = { content: commentText };
    if (replyingTo) payload.parent_id = replyingTo.comment_id;
    if (commentAttachments.length) payload.attachments = commentAttachments.map(a => a.attachment_id);
    const { data } = await api.post(`/news/posts/${postId}/comments`, payload);
    setComments(prev => [...prev, data]);
    setCommentText('');
    setCommentAttachments([]);
    setReplyingTo(null);
    return data;
  }, [commentText, commentAttachments, replyingTo]);

  const deleteComment = useCallback(async (commentId) => {
    await api.delete(`/news/comments/${commentId}`);
    setComments(prev => prev.filter(c => c.comment_id !== commentId));
  }, []);

  const toggleReaction = useCallback(async (postId, type) => {
    await api.post(`/news/posts/${postId}/reactions`, { reaction_type: type });
    // Caller is responsible for refetching the post itself if it needs
    // the updated `user_reaction` / `reaction_counts` fields. Returning
    // the fresh post here keeps the call-site flexible.
    try {
      const { data } = await api.get(`/news/posts/${postId}`);
      return data;
    } catch { return null; }
  }, []);

  const askQuestion = useCallback(async (postId) => {
    const text = questionText.trim();
    if (!text) return null;
    const { data } = await api.post(`/news/posts/${postId}/questions`, { text });
    setQuestions(prev => [...prev, data]);
    setQuestionText('');
    return data;
  }, [questionText]);

  const answerQuestion = useCallback(async (questionId, postId, answer) => {
    if (!answer) return;
    await api.post(`/news/questions/${questionId}/answer`, { answer });
    const { data } = await api.get(`/news/posts/${postId}/questions`);
    setQuestions(data);
  }, []);

  const upvoteQuestion = useCallback(async (questionId) => {
    const { data } = await api.post(`/news/questions/${questionId}/upvote`);
    setQuestions(prev => prev.map(x => x.question_id === questionId
      ? { ...x, upvote_count: data.upvote_count, user_upvoted: data.user_upvoted }
      : x
    ));
  }, []);

  const runSentiment = useCallback(async (postId) => {
    const { data } = await api.get(`/news/posts/${postId}/sentiment`);
    setSentiment(data);
    return data;
  }, []);

  // Clean up transient draft if the user navigates away — the comments &
  // questions stay around so the optimistic update keeps working when the
  // user reopens the same post.
  useEffect(() => () => {
    setCommentText('');
    setCommentAttachments([]);
    setReplyingTo(null);
    setQuestionText('');
  }, []);

  return {
    comments, setComments,
    commentText, setCommentText,
    commentAttachments, setCommentAttachments,
    replyingTo, setReplyingTo,
    questions, setQuestions,
    questionText, setQuestionText,
    sentiment, setSentiment,
    load, reset,
    addComment, deleteComment, toggleReaction,
    askQuestion, answerQuestion, upvoteQuestion,
    runSentiment,
  };
}
