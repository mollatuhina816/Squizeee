import StudentDashboard from '../student-dashboard';

export default function StudentProfilePage() {
  return <main className="student-page"><header className="student-page-header"><a href="/" className="wordmark"><span className="mark">Q</span>Quizeee</a><nav aria-label="Student navigation"><a href="/">My account</a><a href="/join">Join a quiz</a></nav></header><h1>My student dashboard</h1><StudentDashboard/></main>;
}
