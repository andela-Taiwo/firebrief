import { Route, Routes } from "react-router-dom";
import { Ask } from "./screens/Ask";
import { SignIn } from "./screens/SignIn";
import { Verify } from "./screens/Verify";
import { About, Accessibility, Help, Landing, NotFound, SignedOut } from "./screens/pages";

export const APP_ROUTES = ["/sign-in", "/auth/verify", "/ask", "/signed-out"];

export function App() {
  return (
    <Routes>
      <Route path="/" element={<Landing />} />
      <Route path="/about" element={<About />} />
      <Route path="/help" element={<Help />} />
      <Route path="/accessibility" element={<Accessibility />} />
      <Route path="/sign-in" element={<SignIn />} />
      <Route path="/auth/verify" element={<Verify />} />
      <Route path="/ask" element={<Ask />} />
      <Route path="/signed-out" element={<SignedOut />} />
      <Route path="*" element={<NotFound />} />
    </Routes>
  );
}
