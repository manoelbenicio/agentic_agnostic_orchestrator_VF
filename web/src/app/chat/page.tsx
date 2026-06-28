import { ChatConsole } from "@/components/chat/ChatConsole";

export const metadata = {
  title: "Chat Console - AOP",
  description: "AI runtime chat console for the AOP control plane.",
};

export default function ChatPage() {
  return <ChatConsole />;
}
