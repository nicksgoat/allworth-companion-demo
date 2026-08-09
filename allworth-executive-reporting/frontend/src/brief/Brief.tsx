// Executive Brief — CEO inbox operating system. Mounts the inbox dashboard
// inside the portal chrome (SideNav rail, has-sidenav offset). Runs in mock
// mode: bundled sample emails, actions persisted to localStorage. Live Graph
// and Claude analysis land behind /brief/api (see backend/brief/routes.py).
import { ToolPage } from '../components/ToolPage';
import { Dashboard } from './components/dashboard';
import './brief.css';

export default function Brief() {
  return (
    <ToolPage
      eyebrow="Executive workflow"
      title="Executive Brief"
      description="Triage decisions, responses, and follow-up from the executive inbox."
      width="wide"
    >
      <div className="brief-app">
        <Dashboard />
      </div>
    </ToolPage>
  );
}
