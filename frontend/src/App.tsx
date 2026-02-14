import WorkstationLayout from "./components/layout/WorkstationLayout";
import ConversationSidebar from "./components/sidebar/ConversationSidebar";
import ChatArea from "./components/chat/ChatArea";
import TaskPanel from "./components/tasks/TaskPanel";
import CorpusViewer from "./components/corpus/CorpusViewer";
import { useCorpusStore } from "./stores/corpusStore";

export default function App() {
  const activeFile = useCorpusStore((s) => s.activeFile);

  return (
    <WorkstationLayout
      sidebar={<ConversationSidebar />}
      main={<ChatArea />}
      panel={<TaskPanel />}
      corpusPanel={<CorpusViewer />}
      showCorpus={!!activeFile}
    />
  );
}
