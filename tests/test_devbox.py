import io
import json
import os
import runpy
import subprocess
import unittest
from pathlib import Path
from unittest import mock


DEVBOX = runpy.run_path(str(Path(__file__).parents[1] / "bin" / "devbox"), run_name="devbox_test")


def new_devbox(command="start", **kwargs):
    return DEVBOX["DevBox"](command, **kwargs)


class ContainerPathTest(unittest.TestCase):
    def test_converts_windows_drive_path_to_absolute_posix_path(self):
        container_path = DEVBOX["container_path"]

        self.assertEqual(container_path(r"C:\Users\alex"), "/c/Users/alex")
        self.assertEqual(container_path(r"D:\projects\devbox"), "/d/projects/devbox")

    def test_preserves_posix_path(self):
        self.assertEqual(DEVBOX["container_path"]("/home/alex/devbox"), "/home/alex/devbox")

    def test_devbox_uses_converted_container_paths(self):
        devbox_class = DEVBOX["DevBox"]

        with mock.patch.dict(devbox_class.__init__.__globals__, {"project_mount_path": lambda _path: r"C:\Users"}):
            instance = devbox_class("start", project_dir=r"C:\Users\alex")

        self.assertEqual(instance.project_mount_dir, r"C:\Users")
        self.assertEqual(instance.project_container_mount_dir, "/c/Users")
        self.assertEqual(instance.project_container_dir, "/c/Users/alex")


class HelperTest(unittest.TestCase):
    def test_path_is_within_includes_parent_and_children_but_not_siblings(self):
        path_is_within = DEVBOX["path_is_within"]

        self.assertTrue(path_is_within("/project", "/project"))
        self.assertTrue(path_is_within("/project/src", "/project"))
        self.assertFalse(path_is_within("/project-other", "/project"))

    def test_normalizes_wsl_mount_sources(self):
        normalize = DEVBOX["normalize_container_path"]

        self.assertEqual(
            normalize(r"\\wsl.localhost\Ubuntu\home\alex\devbox"),
            "/home/alex/devbox",
        )
        self.assertEqual(normalize("/home/alex/devbox"), "/home/alex/devbox")

    def test_yaml_quote_escapes_quotes_and_backslashes(self):
        self.assertEqual(DEVBOX["yaml_quote"]('a\\b"c'), '"a\\\\b\\"c"')

    def test_find_container_cli_prefers_configuration_then_discovery_order(self):
        find_container_cli = DEVBOX["find_container_cli"]
        globals_ = find_container_cli.__globals__

        with mock.patch.dict(os.environ, {"CONTAINER_CLI": "custom-cli"}, clear=True):
            self.assertEqual(find_container_cli(), "custom-cli")

        with mock.patch.dict(os.environ, {}, clear=True), mock.patch.object(
            globals_["shutil"], "which", side_effect=lambda name: "/usr/bin/docker" if name == "docker" else None
        ) as which:
            self.assertEqual(find_container_cli(), "/usr/bin/docker")
            self.assertEqual([call.args[0] for call in which.call_args_list], ["wslc.exe", "wslc", "docker"])

    def test_configured_auth_envs_ignores_empty_values(self):
        configured_auth_envs = DEVBOX["configured_auth_envs"]
        with mock.patch.dict(
            os.environ,
            {"DEVBOX_AUTH_OPENAI_API_KEY": "secret", "DEVBOX_AUTH_ANTHROPIC_API_KEY": ""},
            clear=True,
        ):
            self.assertEqual(
                configured_auth_envs(),
                {"OPENAI_API_KEY": ("DEVBOX_AUTH_OPENAI_API_KEY", "secret")},
            )


class InspectTest(unittest.TestCase):
    def test_inspect_objects_accepts_docker_list_and_podman_object(self):
        instance = new_devbox(container_cli="docker")

        for payload, expected in [([{"Id": "one"}], [{"Id": "one"}]), ({"Id": "one"}, [{"Id": "one"}])]:
            with self.subTest(payload=payload), mock.patch.object(
                instance,
                "run_cli",
                return_value=subprocess.CompletedProcess([], 0, stdout=json.dumps(payload)),
            ):
                self.assertEqual(instance.inspect_objects("devbox"), expected)

    def test_inspect_objects_rejects_failed_empty_and_invalid_responses(self):
        instance = new_devbox(container_cli="docker")

        for returncode, stdout in [(1, "[]"), (0, ""), (0, "not-json")]:
            with self.subTest(returncode=returncode, stdout=stdout), mock.patch.object(
                instance,
                "run_cli",
                return_value=subprocess.CompletedProcess([], returncode, stdout=stdout),
            ):
                self.assertEqual(instance.inspect_objects("devbox"), [])

    def test_workspace_mount_selects_mount_containing_workdir(self):
        instance = new_devbox()
        container = {
            "Config": {"WorkingDir": "/workspace/repo"},
            "Mounts": [
                {"Source": "/tmp/unrelated", "Destination": "/tmp"},
                {"Source": "/host/workspace", "Destination": "/workspace"},
            ],
        }

        with mock.patch.object(instance, "container_inspect", return_value=container):
            self.assertEqual(instance.container_workspace_mount(), ("/host/workspace", "/workspace"))

    def test_container_directory_rejects_path_outside_workspace(self):
        instance = new_devbox()
        globals_ = instance.container_directory.__globals__

        with mock.patch.object(instance, "container_workspace_mount", return_value=("/project", "/project")), mock.patch.dict(
            globals_, {"canonical_dir": lambda _path, _description: "/elsewhere"}
        ), mock.patch("sys.stderr", new_callable=io.StringIO) as stderr:
            with self.assertRaisesRegex(SystemExit, "1"):
                instance.container_directory("/elsewhere")

        self.assertIn("outside the started workspace", stderr.getvalue())

    def test_container_directory_converts_windows_relative_separators(self):
        instance = new_devbox()
        globals_ = instance.container_directory.__globals__

        with mock.patch.object(
            instance,
            "container_workspace_mount",
            return_value=(r"C:\Users\alex", "/c/Users/alex"),
        ), mock.patch.dict(
            globals_,
            {
                "canonical_dir": lambda _path, _description: r"C:\Users\alex\Developer\monix",
                "path_is_within": lambda _path, _parent: True,
            },
        ), mock.patch.object(globals_["os"], "name", "nt"), mock.patch.object(
            globals_["os"].path, "relpath", return_value=r"Developer\monix"
        ):
            container_directory = instance.container_directory(r"C:\Users\alex\Developer\monix")

        self.assertEqual(container_directory, "/c/Users/alex/Developer/monix")

    def test_container_directory_preserves_backslashes_in_posix_filename(self):
        instance = new_devbox()
        globals_ = instance.container_directory.__globals__

        with mock.patch.object(
            instance,
            "container_workspace_mount",
            return_value=("/home/alex", "/home/alex"),
        ), mock.patch.dict(
            globals_,
            {
                "canonical_dir": lambda _path, _description: "/home/alex/project\\name",
                "path_is_within": lambda _path, _parent: True,
            },
        ), mock.patch.object(globals_["os"], "name", "posix"), mock.patch.object(
            globals_["os"].path, "relpath", return_value="project\\name"
        ):
            container_directory = instance.container_directory("/home/alex/project\\name")

        self.assertEqual(container_directory, "/home/alex/project\\name")


class ConfigurationTest(unittest.TestCase):
    def test_start_and_compose_use_default_agent_port(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            for command in ("start", "compose"):
                with self.subTest(command=command):
                    instance = new_devbox(command)
                    instance.configure_agent_port()
                    self.assertEqual(instance.agent_port, "10012")

    def test_auth_and_opencode_environment_arguments_are_forwarded(self):
        instance = new_devbox()
        instance.opencode_config_host_dir = "/config"
        globals_ = instance.configure_container_env_args.__globals__

        with mock.patch.dict(
            globals_, {"configured_auth_envs": lambda: {"TOKEN": ("DEVBOX_AUTH_TOKEN", "secret")}}
        ):
            instance.configure_container_env_args()

        self.assertEqual(
            instance.container_env_args,
            ["-e", "TOKEN=secret", "-e", "OPENCODE_CONFIG_DIR=/opt/opencode-config"],
        )

    def test_wireguard_is_disabled_without_configuration(self):
        instance = new_devbox()

        with mock.patch.dict(os.environ, {}, clear=True):
            instance.configure_wireguard()

        self.assertEqual(instance.wireguard_config_host_path, "")
        self.assertEqual(instance.wireguard_args(), [])
        self.assertNotIn("wg-quick", instance.workspace_link_command())

    def test_wireguard_configuration_adds_mount_and_network_admin(self):
        instance = new_devbox(container_cli="podman")
        globals_ = instance.configure_wireguard.__globals__

        with mock.patch.dict(os.environ, {"DEVBOX_WIREGUARD_CONFIG": "~/wg.conf"}, clear=True), mock.patch.dict(
            globals_, {"canonical_file": lambda _path, _description: "/home/alex/wg.conf"}
        ):
            instance.configure_wireguard()

        self.assertEqual(instance.wireguard_config_host_path, "/home/alex/wg.conf")
        self.assertEqual(instance.wireguard_mtu, "1420")
        self.assertEqual(
            instance.wireguard_args(),
            [
                "--cap-add",
                "NET_ADMIN",
                "--sysctl",
                "net.ipv4.conf.all.src_valid_mark=1",
                "-v",
                "/home/alex/wg.conf:/etc/wireguard/devbox.conf:ro",
                "-e",
                "DEVBOX_WIREGUARD_MTU=1420",
            ],
        )
        self.assertTrue(
            instance.workspace_link_command().startswith(
                "wg-quick up /etc/wireguard/devbox.conf && ip link set dev devbox mtu 1420 && "
            )
        )

    def test_wireguard_rejects_invalid_mtu(self):
        instance = new_devbox(container_cli="podman")
        globals_ = instance.configure_wireguard.__globals__

        with mock.patch.dict(
            os.environ,
            {"DEVBOX_WIREGUARD_CONFIG": "/wg.conf", "DEVBOX_WIREGUARD_MTU": "huge"},
            clear=True,
        ), mock.patch.dict(globals_, {"canonical_file": lambda _path, _description: "/wg.conf"}):
            with self.assertRaisesRegex(SystemExit, "DEVBOX_WIREGUARD_MTU"):
                instance.configure_wireguard()

    def test_wireguard_fails_early_with_explanation_on_wslc(self):
        instance = new_devbox(container_cli="wslc.exe")
        globals_ = instance.configure_wireguard.__globals__

        with mock.patch.dict(os.environ, {"DEVBOX_WIREGUARD_CONFIG": "/wg.conf"}, clear=True), mock.patch.dict(
            globals_, {"canonical_file": lambda _path, _description: "/wg.conf"}
        ):
            with self.assertRaisesRegex(SystemExit, "wslc.*NET_ADMIN"):
                instance.configure_wireguard()

    def test_help_env_documents_optional_wireguard_configuration(self):
        help_text = DEVBOX["ENVIRONMENT_HELP"]

        self.assertIn("DEVBOX_WIREGUARD_CONFIG", help_text)
        self.assertIn("DEVBOX_WIREGUARD_MTU", help_text)
        self.assertIn("optional", help_text.lower())


class ContainerExecutionTest(unittest.TestCase):
    def test_start_reports_wireguard_attempt_and_fails_if_container_exits(self):
        instance = new_devbox(container_cli="podman")
        instance.wireguard_config_host_path = "/wg.conf"
        instance.wireguard_mtu = "1420"

        with mock.patch.object(instance, "container_exists", return_value=False), mock.patch.object(
            instance, "create_home_volume"
        ), mock.patch.object(instance, "run_new_container"), mock.patch.object(
            instance,
            "container_inspect",
            return_value={"State": {"Running": False, "ExitCode": 127, "Error": ""}},
        ), mock.patch.object(instance, "container_logs", return_value="wg-quick: not found"), mock.patch(
            "sys.stdout", new_callable=io.StringIO
        ) as stdout, mock.patch("sys.stderr", new_callable=io.StringIO) as stderr:
            with self.assertRaisesRegex(SystemExit, "1"):
                instance.start_container()

        self.assertIn("WireGuard: enabled", stdout.getvalue())
        self.assertIn("attempting connection", stdout.getvalue())
        self.assertIn("exited with status 127", stderr.getvalue())
        self.assertIn("wg-quick: not found", stderr.getvalue())

    def test_windows_uses_subprocess_for_cli_path_containing_spaces(self):
        cli = r"C:\Program Files\WSL\wslc.exe"
        instance = new_devbox("shell", container_cli=cli)
        globals_ = instance.exec_container.__globals__

        with mock.patch.object(globals_["os"], "name", "nt"), mock.patch.object(
            globals_["subprocess"],
            "run",
            return_value=subprocess.CompletedProcess([], 7),
        ) as run, mock.patch.object(globals_["os"], "execvp") as execvp:
            with self.assertRaisesRegex(SystemExit, "7"):
                instance.exec_container(["bash"])

        command = run.call_args.args[0]
        self.assertEqual(command[0], cli)
        self.assertEqual(command[1:3], ["exec", "-it"])
        self.assertEqual(command[-2:], ["/usr/local/bin/devbox-entrypoint", "bash"])
        execvp.assert_not_called()


class ParserTest(unittest.TestCase):
    def test_start_requires_and_parses_project_directory(self):
        namespace = DEVBOX["build_parser"]().parse_args(["start", "."])

        self.assertEqual(namespace.command, "start")
        self.assertEqual(namespace.project_directory, ".")

    def test_exec_preserves_passthrough_arguments(self):
        namespace = DEVBOX["build_parser"]().parse_args(["exec", "python", "-c", "print('ok')"])

        self.assertEqual(namespace.command_args, ["python", "-c", "print('ok')"])

    def test_agent_parses_execution_directory_and_passthrough_arguments(self):
        namespace = DEVBOX["build_parser"]().parse_args(["agent", "-C", "src", "--", "--model", "test"])

        self.assertEqual(namespace.execution_dir, "src")
        self.assertEqual(namespace.command_args, ["--", "--model", "test"])


if __name__ == "__main__":
    unittest.main()
