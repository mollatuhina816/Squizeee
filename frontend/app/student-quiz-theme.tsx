'use client';

export const classLevels = ['5', '6', '7', '8', '9', '10', '11', '12'] as const;
export type ClassLevel = typeof classLevels[number] | '';
export function validClass(value: unknown): ClassLevel {
  return classLevels.includes(value as typeof classLevels[number]) ? value as ClassLevel : '';
}
export function quizTheme(level: ClassLevel) {
  return !level ? 'welcome' : Number(level) <= 7 ? 'school' : Number(level) <= 10 ? 'explorer' : 'science';
}

export function ClassSelector({ value, onChange, disabled = false }: {
  value: ClassLevel; onChange: (value: ClassLevel) => void; disabled?: boolean;
}) {
  return <label className="quiz-class-selector">Choose Class / Category
    <select required value={value} onChange={event => onChange(validClass(event.target.value))} disabled={disabled}>
      <option value="" disabled>Select your class</option>
      {classLevels.map(level => <option key={level} value={level}>Class {level}</option>)}
    </select>
    <small>Your class sets the look of your quiz experience.</small>
  </label>;
}

export function QuizThemeBanner({ level }: { level: ClassLevel }) {
  const theme = quizTheme(level);
  const title = theme === 'school' ? 'Big ideas start with curiosity.' : theme === 'explorer' ? 'Explore. Think. Discover.' : theme === 'science' ? 'Curiosity meets precision.' : 'Your next discovery starts here.';
  const caption = theme === 'school' ? 'A little thinking. A lot of discovery. Let’s learn something new!' : theme === 'explorer' ? 'Connect the dots and put your knowledge to the test.' : theme === 'science' ? 'A focused space for science, problem solving, and NEET preparation.' : 'Choose your class and make this learning space your own.';
  return <div className="quiz-theme-banner">
    <div className="quiz-theme-copy"><span className="quiz-theme-label">{level ? `CLASS ${level} · ${theme === 'school' ? 'LEARNING CLUB' : theme === 'explorer' ? 'DISCOVERY LAB' : 'SCIENCE & NEET'}` : 'WELCOME TO QUIZEEE'}</span><h2>{title}</h2><p>{caption}</p><span className="quiz-theme-pill">{theme === 'science' ? 'Stay curious. Stay focused.' : 'Every question is a new discovery'}</span></div>
    <div className="quiz-theme-art" aria-hidden="true">
      {theme === 'science' ? <svg viewBox="0 0 180 180" className="quiz-atom"><circle cx="90" cy="90" r="8" fill="currentColor"/><g fill="none" stroke="currentColor" strokeWidth="2"><ellipse cx="90" cy="90" rx="75" ry="27"/><ellipse cx="90" cy="90" rx="75" ry="27" transform="rotate(60 90 90)"/><ellipse cx="90" cy="90" rx="75" ry="27" transform="rotate(120 90 90)"/></g><circle cx="165" cy="90" r="5" fill="currentColor"/><circle cx="53" cy="26" r="5" fill="currentColor"/></svg> : <svg viewBox="0 0 180 180" className="quiz-school-art"><path d="M28 52 Q58 38 90 55 Q122 38 152 52 V133 Q122 119 90 137 Q58 119 28 133Z" fill="white" stroke="currentColor" strokeWidth="4"/><path d="M90 55V137M43 70L74 74M43 86L74 90M106 74L137 70M106 90L137 86" stroke="currentColor" strokeWidth="3" fill="none"/><path d="m125 19 6 12 14 2-10 10 2 14-12-7-12 7 2-14-10-10 14-2Z" fill="#ffcb59"/><path d="m22 20 3 8 9 2-9 3-3 9-3-9-9-3 9-2Z" fill="currentColor"/><circle cx="150" cy="152" r="7" fill="#ffcb59"/></svg>}
      <span className="quiz-art-dot quiz-art-dot-one"/><span className="quiz-art-dot quiz-art-dot-two"/>
    </div>
  </div>;
}
