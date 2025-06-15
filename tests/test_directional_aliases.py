"""Tests for directional alias functionality in DanbooruTagGraph."""

import unittest
from danbooru_tag_graph import DanbooruTagGraph


class TestDirectionalAliases(unittest.TestCase):
    """Test directional alias functionality."""

    def setUp(self):
        """Set up test case."""
        self.graph = DanbooruTagGraph()

    def test_add_directional_alias(self):
        """Test adding directional aliases (antecedent -> consequent)."""
        # Add the directional alias: ugly_man -> ugly_bastard
        self.graph.add_alias("ugly_man", "ugly_bastard")
        
        # Verify the alias relationship
        self.assertEqual(self.graph.get_aliases("ugly_man"), ["ugly_bastard"])
        self.assertEqual(self.graph.get_aliases("ugly_bastard"), [])  # No outgoing aliases

    def test_get_aliased_from(self):
        """Test getting incoming aliases (what is aliased TO this tag)."""
        # Add the directional alias: ugly_man -> ugly_bastard
        self.graph.add_alias("ugly_man", "ugly_bastard")
        
        # Verify incoming aliases (should work with default include_deprecated=True)
        self.assertEqual(self.graph.get_aliased_from("ugly_bastard"), ["ugly_man"])
        self.assertEqual(self.graph.get_aliased_from("ugly_man"), [])  # No incoming aliases

    def test_get_aliased_from_with_deprecated(self):
        """Test getting incoming aliases with deprecated antecedents."""
        # Add tags with explicit deprecated status
        self.graph.add_tag("ugly_man", is_deprecated=True)
        self.graph.add_tag("ugly_bastard", is_deprecated=False)
        self.graph.add_alias("ugly_man", "ugly_bastard")
        
        # Should include deprecated antecedent by default
        self.assertEqual(self.graph.get_aliased_from("ugly_bastard"), ["ugly_man"])
        
        # Should still include when explicitly requested
        self.assertEqual(self.graph.get_aliased_from("ugly_bastard", include_deprecated=True), ["ugly_man"])
        
        # Should exclude when explicitly not requested
        self.assertEqual(self.graph.get_aliased_from("ugly_bastard", include_deprecated=False), [])

    def test_is_canonical(self):
        """Test canonical tag detection."""
        # Add tags and alias
        self.graph.add_tag("ugly_man")
        self.graph.add_tag("ugly_bastard")
        self.graph.add_alias("ugly_man", "ugly_bastard")
        
        # Test canonical status
        self.assertFalse(self.graph.is_canonical("ugly_man"))      # Has outgoing alias
        self.assertTrue(self.graph.is_canonical("ugly_bastard"))   # No outgoing alias
        self.assertTrue(self.graph.is_canonical("nonexistent"))   # Non-existent are canonical

    def test_resolve_to_canonical(self):
        """Test resolving tags to their canonical forms."""
        # Create alias chain: old_tag -> new_tag -> canonical_tag
        self.graph.add_alias("old_tag", "new_tag")
        self.graph.add_alias("new_tag", "canonical_tag")
        
        # Test resolution
        self.assertEqual(self.graph._resolve_to_canonical("old_tag"), "canonical_tag")
        self.assertEqual(self.graph._resolve_to_canonical("new_tag"), "canonical_tag")
        self.assertEqual(self.graph._resolve_to_canonical("canonical_tag"), "canonical_tag")

    def test_expand_tags_with_directional_aliases(self):
        """Test tag expansion with directional aliases."""
        # Set up test data
        self.graph.add_tag("ugly_man")
        self.graph.add_tag("ugly_bastard")
        self.graph.add_tag("male")
        
        # Add directional alias and implication
        self.graph.add_alias("ugly_man", "ugly_bastard")
        self.graph.add_implication("ugly_bastard", "male")
        
        # Test expansion from antecedent tag
        expanded, frequencies = self.graph.expand_tags(["ugly_man"])
        
        # Should resolve to canonical form and include implications
        expected_tags = {"ugly_bastard", "male", "ugly_man"}  # Includes alias group
        self.assertEqual(expanded, expected_tags)
        
        # Frequency should be on canonical form
        self.assertEqual(frequencies["ugly_bastard"], 1)
        self.assertEqual(frequencies["male"], 1)

    def test_alias_chain_resolution(self):
        """Test resolving complex alias chains."""
        # Create chain: deprecated -> old -> current -> canonical
        self.graph.add_alias("deprecated", "old")
        self.graph.add_alias("old", "current")
        self.graph.add_alias("current", "canonical")
        
        # All should resolve to canonical
        self.assertEqual(self.graph._resolve_to_canonical("deprecated"), "canonical")
        self.assertEqual(self.graph._resolve_to_canonical("old"), "canonical")
        self.assertEqual(self.graph._resolve_to_canonical("current"), "canonical")
        self.assertEqual(self.graph._resolve_to_canonical("canonical"), "canonical")

    def test_alias_cycle_handling(self):
        """Test handling of alias cycles."""
        # Create a cycle: tag_a -> tag_b -> tag_a
        self.graph.add_alias("tag_a", "tag_b")
        self.graph.add_alias("tag_b", "tag_a")
        
        # Should not crash and return original tag
        self.assertEqual(self.graph._resolve_to_canonical("tag_a"), "tag_a")
        self.assertEqual(self.graph._resolve_to_canonical("tag_b"), "tag_b")

    def test_multiple_aliases_from_same_antecedent(self):
        """Test multiple consequents from same antecedent."""
        # Add multiple aliases from same antecedent
        self.graph.add_alias("old_tag", "new_tag_1")
        self.graph.add_alias("old_tag", "new_tag_2")
        
        # Should get all consequents
        aliases = self.graph.get_aliases("old_tag")
        self.assertIn("new_tag_1", aliases)
        self.assertIn("new_tag_2", aliases)
        self.assertEqual(len(aliases), 2)

    def test_multiple_antecedents_to_same_consequent(self):
        """Test multiple antecedents pointing to same consequent."""
        # Add multiple aliases to same consequent
        self.graph.add_alias("old_tag_1", "canonical")
        self.graph.add_alias("old_tag_2", "canonical")
        
        # Should get all antecedents
        aliased_from = self.graph.get_aliased_from("canonical")
        self.assertIn("old_tag_1", aliased_from)
        self.assertIn("old_tag_2", aliased_from)
        self.assertEqual(len(aliased_from), 2)

    def test_alias_group_connectivity(self):
        """Test alias group detection with directional aliases."""
        # Create connected alias group: a -> b -> c, d -> b
        self.graph.add_alias("a", "b")
        self.graph.add_alias("b", "c")
        self.graph.add_alias("d", "b")
        
        # All should be in same alias group
        group_a = self.graph.get_alias_group("a")
        group_b = self.graph.get_alias_group("b")
        group_c = self.graph.get_alias_group("c")
        group_d = self.graph.get_alias_group("d")
        
        expected_group = {"a", "b", "c", "d"}
        self.assertEqual(group_a, expected_group)
        self.assertEqual(group_b, expected_group)
        self.assertEqual(group_c, expected_group)
        self.assertEqual(group_d, expected_group)

    def test_backward_compatibility_warning(self):
        """Test that the API change is documented."""
        # This test documents the breaking change
        # Old bidirectional behavior:
        # self.graph.add_alias("tag1", "tag2")  # Would create tag1 <-> tag2
        # self.graph.get_aliases("tag1")       # Would return ["tag2"]
        # self.graph.get_aliases("tag2")       # Would return ["tag1"]
        
        # New directional behavior:
        self.graph.add_alias("antecedent", "consequent")  # Creates antecedent -> consequent
        self.assertEqual(self.graph.get_aliases("antecedent"), ["consequent"])
        self.assertEqual(self.graph.get_aliases("consequent"), [])
        
        # Use get_aliased_from for reverse direction
        self.assertEqual(self.graph.get_aliased_from("consequent"), ["antecedent"])
        self.assertEqual(self.graph.get_aliased_from("antecedent"), [])

    def test_real_world_example(self):
        """Test with real Danbooru example from the bug report."""
        # Based on the bug report example
        self.graph.add_alias("ugly_man", "ugly_bastard")
        
        # Test correct behavior
        self.assertEqual(self.graph.get_aliases("ugly_man"), ["ugly_bastard"])
        self.assertEqual(self.graph.get_aliases("ugly_bastard"), [])
        
        # Test canonical detection
        self.assertFalse(self.graph.is_canonical("ugly_man"))      # antecedent
        self.assertTrue(self.graph.is_canonical("ugly_bastard"))   # consequent
        
        # Test reverse lookup
        self.assertEqual(self.graph.get_aliased_from("ugly_bastard"), ["ugly_man"])
        self.assertEqual(self.graph.get_aliased_from("ugly_man"), [])

    def test_bug_report_reproduction(self):
        """Test the exact scenario from the bug report."""
        # Reproduce the exact bug report scenario
        graph = DanbooruTagGraph()
        graph.add_tag("ugly_man", is_deprecated=True, fetched=True)
        graph.add_tag("ugly_bastard", is_deprecated=False, fetched=True)
        graph.add_alias("ugly_man", "ugly_bastard")  # ugly_man -> ugly_bastard

        # Test the methods from the bug report
        self.assertEqual(graph.get_aliases("ugly_man"), ["ugly_bastard"])  # Should work
        self.assertEqual(graph.get_aliased_from("ugly_bastard"), ["ugly_man"])  # Was broken, now fixed

        # Verify graph structure (from bug report verification)
        out_edges = list(graph.graph.out_edges("ugly_man", data=True))
        self.assertEqual(out_edges, [("ugly_man", "ugly_bastard", {"edge_type": "alias"})])
        
        in_edges = list(graph.graph.in_edges("ugly_bastard", data=True))
        self.assertEqual(in_edges, [("ugly_man", "ugly_bastard", {"edge_type": "alias"})])


if __name__ == '__main__':
    unittest.main() 