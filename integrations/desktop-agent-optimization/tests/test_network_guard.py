import unittest

from verification.network_guard import validate_destination


class NetworkGuardTests(unittest.TestCase):
    def test_only_the_mock_endpoint_is_allowed(self):
        """Given the allowed mock port, when localhost is requested, then it passes validation."""
        validate_destination(('127.0.0.1', 4567), 4567)

    def test_auth_routing_cannot_connect_to_external_provider(self):
        """Given subscription headers select an external provider, when it connects, then the guard rejects it."""
        for target in [('chatgpt.com', 443), ('104.18.32.47', 443), ('127.0.0.1', 8787)]:
            with self.subTest(target=target), self.assertRaises(OSError):
                validate_destination(target, 4567)

    def test_localhost_lookalike_is_rejected(self):
        """Given an endpoint name resembles localhost, when checked, then it is still rejected."""
        with self.assertRaises(OSError):
            validate_destination(('localhost.example.invalid', 4567), 4567)


if __name__ == '__main__':
    unittest.main()
