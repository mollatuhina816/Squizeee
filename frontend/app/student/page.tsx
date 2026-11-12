import StudentDashboard from '../student-dashboard';

export default function StudentProfilePage() {
  return <main className="student-page sd-page"><header className="student-page-header"><a href="/" className="wordmark"><span className="mark">Q</span>Quizeee</a><nav aria-label="Student navigation"><a href="/">My account</a><a href="/join">Join a quiz</a></nav></header><div className="page-heading sd-pagehead"><div><span className="eyebrow">YOUR LEARNING SPACE</span><h1>My learning hub</h1><p>Small challenges. Meaningful progress. Your next discovery starts here.</p></div></div><StudentDashboard/></main>;
}
