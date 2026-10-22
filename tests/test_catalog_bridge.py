import copy
import unittest
from types import SimpleNamespace

from tools.catalog_bridge import attach_catalog, normalize, synthetic_catalog


class CatalogTests(unittest.TestCase):
    def test_preserves_cfg_and_external_calls(self):
        catalog = synthetic_catalog()
        catalog["functions"][0]["calls_to"] = [0x9000]
        plan = normalize(catalog)
        self.assertEqual(plan["functions"][0]["blocks"], [[0x1000, 0x1009, [], 1]])
        self.assertEqual(plan["unresolved_calls"], [0x9000])

    def test_invalid_catalogs(self):
        original = synthetic_catalog()
        variants = []
        c = copy.deepcopy(original)
        c["functions"] *= 2
        variants.append(c)
        c = copy.deepcopy(original)
        c["functions"][0]["blocks"][0][1] += 1
        variants.append(c)
        c = copy.deepcopy(original)
        c["functions"][0]["address"] += 1
        variants.append(c)
        c = copy.deepcopy(original)
        c["image_base"] = True
        variants.append(c)
        c = copy.deepcopy(original)
        c["functions"][0]["blocks"].append([0x1000, 0x1009, [], 1])
        variants.append(c)
        for catalog in variants:
            with self.subTest(catalog=catalog), self.assertRaises(ValueError):
                normalize(catalog)

    def test_redecodes_only_saved_ranges(self):
        class Decoder:
            def disasm(self, data, start):
                self.request = (data, start)
                return [SimpleNamespace(address=start, size=4),
                        SimpleNamespace(address=start + 4, size=4),
                        SimpleNamespace(address=start + 8, size=1)]

        def forbidden(*args):
            raise AssertionError("discovery must never run")

        lifter = SimpleNamespace(md=Decoder(), secs=[(".text", 0x1000, 9, b"x" * 9)],
                                 discover=forbidden)
        attach_catalog(lifter, synthetic_catalog())
        blocks, calls = lifter.discover(0x1000)
        self.assertEqual(len(blocks[0x1000]), 3)
        self.assertEqual(lifter.md.request, (b"x" * 9, 0x1000))
        self.assertEqual(calls, set())
        with self.assertRaises(KeyError):
            lifter.discover(0x2000)

    def test_incomplete_decode_rejected(self):
        lifter = SimpleNamespace(md=SimpleNamespace(disasm=lambda data, start: []),
                                 secs=[(".text", 0x1000, 9, b"x" * 9)])
        attach_catalog(lifter, synthetic_catalog())
        with self.assertRaises(ValueError):
            lifter.discover(0x1000)

    def test_missing_section_rejected(self):
        lifter = SimpleNamespace(md=None, secs=[])
        attach_catalog(lifter, synthetic_catalog())
        with self.assertRaises(ValueError):
            lifter.discover(0x1000)


if __name__ == "__main__":
    unittest.main()
