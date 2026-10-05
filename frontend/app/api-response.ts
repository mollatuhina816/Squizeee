export async function readApiResponse<T>(response: Response): Promise<T> {
  let data: unknown;
  try {
    data = await response.json();
  } catch {
    throw new Error(response.ok
      ? 'The server returned an invalid response. Please try again.'
      : 'Unable to reach the application service. Please try again shortly.');
  }
  if (!response.ok) {
    const detail = data && typeof data === 'object' && 'detail' in data ? data.detail : null;
    if (Array.isArray(detail)) {
      const messages = detail.map((issue: { loc?: (string | number)[]; msg?: string }) => {
        const loc = issue.loc || [];
        const questionIndex = loc.indexOf('questions');
        const label = questionIndex >= 0 && typeof loc[questionIndex + 1] === 'number'
          ? `Question ${Number(loc[questionIndex + 1]) + 1}: ` : '';
        return label + (issue.msg || 'Please check this field.').replace(/^Value error, /, '');
      });
      if (messages.length) throw new Error(messages.join(' '));
    }
    throw new Error(typeof detail === 'string' ? detail : response.status >= 500
      ? 'The application service is temporarily unavailable. Please try again shortly.'
      : 'Please check the form and try again.');
  }
  return data as T;
}
