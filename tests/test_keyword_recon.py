import unittest

from utils.keyword_recon import extract_api_paths, extract_keyword_contexts, extract_keyword_strings


class KeywordReconTests(unittest.TestCase):
    def test_extract_keyword_strings_keeps_human_readable_hits(self):
        text = '"AgentId.CODER" "oauth login from coder" "/api/v0/chat/completion"'
        values = extract_keyword_strings(text, ["coder", "api"])
        self.assertIn("AgentId.CODER", values)
        self.assertIn("oauth login from coder", values)

    def test_extract_api_paths(self):
        text = '"/api/v0/chat/completion" "/api/v0/client/settings"'
        values = extract_api_paths(text)
        self.assertIn("/api/v0/chat/completion", values)
        self.assertIn("/api/v0/client/settings", values)

    def test_extract_keyword_contexts(self):
        text = "before oauth login from coder route to coder after sign in"
        contexts = extract_keyword_contexts(text, ["coder"])
        self.assertIn("coder", contexts)
        self.assertTrue(any("route to coder" in item for item in contexts["coder"]))


if __name__ == "__main__":
    unittest.main()
