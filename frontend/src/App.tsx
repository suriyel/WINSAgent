import WorkstationLayout from "./components/layout/WorkstationLayout";
import ConversationSidebar from "./components/sidebar/ConversationSidebar";
import ChatArea from "./components/chat/ChatArea";
import TaskPanel from "./components/tasks/TaskPanel";

export default function App() {
  return (
    <WorkstationLayout
      sidebar={<ConversationSidebar />}
      main={<ChatArea />}
      panel={<TaskPanel />}
    />
  );
}
