export function renamedAnswers(options: string[], answers: string[], next: string[]): string[] {
  return answers.map(answer => next.includes(answer) ? answer : next[options.indexOf(answer)])
    .filter((answer): answer is string => typeof answer === 'string' && !!answer.trim())
    .filter((answer, index, all) => all.indexOf(answer) === index);
}

export function cleanQuestion<T extends { options: string[]; correct_answers: string[] }>(question: T): T {
  return { ...question, options: question.options.map(x => x.trim()).filter(Boolean),
    correct_answers: question.correct_answers.map(x => x.trim()).filter(Boolean) };
}
