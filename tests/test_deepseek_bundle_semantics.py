import unittest

from utils.bundle_inspector import analyze_js_bundle
from utils.deepseek_bundle_semantics import extract_deepseek_bundle_semantics


class DeepSeekBundleSemanticsTests(unittest.TestCase):
    def test_extracts_route_vision_and_api_semantics(self):
        sample = """
        let nv={ROOT:"/",AGENT:"/a/:agentId",AGENT_SESSION:"/a/:agentId/s/:sessionId"};
        targetBeforeOauthLoginStorageHandle.get() ? e(nv.AGENT,{agentId:O.FM.AgentId.CODER}) : e(nv.ROOT)
        sd={resolveForNewSession:(e,t)=>e,findVisionModel:e=>e.find(e=>e.enabled&&e.switchable&&!!(e.file_feature?.vision))}
        modelSwitchVisUploadTooltip:(e,t)=>"Upload docs or images"
        modelSwitchNoTextImagesBanner:e=>"No text found. Try "+e
        setAgentPrompt("x"); clearAgentPrompt();
        "/api/v0/chat/completion"; "/api/v0/chat/resume_stream"; "/api/v0/file/upload_file";
        "/api/v0/share/create"; "/api/v0/client/settings";
        """
        signals = extract_deepseek_bundle_semantics(sample)
        self.assertIn("CODER", signals["agent_ids"])
        self.assertIn("/a/:agentId", signals["route_patterns"])
        self.assertIn("/a/:agentId/s/:sessionId", signals["route_patterns"])
        self.assertIn("/api/v0/chat/completion", signals["api_paths"])
        self.assertIn("api/v0/chat", signals["api_families"])
        self.assertTrue(any("file_feature" in value for value in signals["vision_signals"]))
        self.assertTrue(any("CODER 已进入 Agent 路由体系" in value for value in signals["hidden_capabilities"]))

    def test_bundle_inspector_surfaces_semantics(self):
        sample = """
        commit_datetime:"2026/04/16 13:01:46"
        let nv={AGENT:"/a/:agentId",AGENT_SESSION:"/a/:agentId/s/:sessionId"};
        AgentId.CODER;
        findVisionModel:e=>e.find(e=>e.enabled&&e.switchable&&!!(e.file_feature?.vision))
        "/api/v0/chat/completion"; "/api/v0/client/settings";
        """
        insights = analyze_js_bundle("main.e0f8beaa34.js", sample)
        self.assertEqual(insights["bundle_role"], "application_bundle")
        self.assertIn("api/v0/chat", insights["api_families"])
        self.assertIn("/a/:agentId", insights["route_patterns"])
        self.assertTrue(any("Vision" in value or "vision" in value for value in insights["hidden_capabilities"]))


if __name__ == "__main__":
    unittest.main()
