import unittest
from pathlib import Path
from unittest import mock

from scenarios._shared import media
from scenarios.tests.fixtures import temporary_directory


class MediaCleanupTests(unittest.TestCase):
    def sharing_error(self):
        error = PermissionError("Unit-test transient Windows sharing violation")
        error.winerror = 32
        return error

    def test_cleanup_retries_only_transient_windows_sharing_errors(self):
        with temporary_directory() as directory:
            real_remove = media.shutil.rmtree
            attempts = []

            def remove(path):
                attempts.append(path)
                if len(attempts) == 1:
                    raise self.sharing_error()
                real_remove(path)

            with mock.patch.object(media.shutil, "rmtree", side_effect=remove), mock.patch.object(media.time, "sleep") as sleep:
                with media._staging(Path(directory)) as staging:
                    staging.joinpath("source.png").write_bytes(b"synthetic temporary")
                self.assertFalse(staging.exists())
                self.assertEqual(len(attempts), 2)
                sleep.assert_called_once_with(0.2)

    def test_persistent_sharing_error_is_not_silently_swallowed(self):
        with temporary_directory() as directory:
            with mock.patch.object(media.shutil, "rmtree", side_effect=self.sharing_error()) as remove, mock.patch.object(media.time, "sleep"):
                with self.assertRaises(PermissionError):
                    with media._staging(Path(directory)):
                        pass
                self.assertEqual(remove.call_count, 5)

    def test_other_cleanup_errors_are_not_retried(self):
        with temporary_directory() as directory:
            with mock.patch.object(media.shutil, "rmtree", side_effect=PermissionError("Not a sharing violation")) as remove, mock.patch.object(media.time, "sleep") as sleep:
                with self.assertRaises(PermissionError):
                    with media._staging(Path(directory)):
                        pass
                remove.assert_called_once()
                sleep.assert_not_called()


if __name__ == "__main__":
    unittest.main()
