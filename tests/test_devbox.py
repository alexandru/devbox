import io
import json
import os
import runpy
import subprocess
import tempfile
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
    def test_dockerfile_uses_portable_default_shell(self):
        dockerfile = (Path(__file__).parents[1] / "Dockerfile").read_text()

        self.assertNotIn("\nSHELL ", dockerfile)
        self.assertIn("ENV SHELL=/bin/bash", dockerfile)

    def test_dockerfile_installs_jvm_build_tools_with_sdkman(self):
        dockerfile = (Path(__file__).parents[1] / "Dockerfile").read_text()

        self.assertIn('source "$SDKMAN_DIR/bin/sdkman-init.sh"', dockerfile)
        for candidate in ("maven", "sbt", "scalacli", "gradle"):
            with self.subTest(candidate=candidate):
                self.assertIn(f"sdk install {candidate}", dockerfile)

    def test_dockerfile_disables_cellar_telemetry_as_dev_user(self):
        dockerfile = (Path(__file__).parents[1] / "Dockerfile").read_text()

        self.assertRegex(
            dockerfile,
            r"USER dev[\s\S]+RUN cs install --contrib cellar && \\\n+    cellar telemetry disable",
        )

    def test_dockerfile_installs_opencode_as_dev_in_home(self):
        dockerfile = (Path(__file__).parents[1] / "Dockerfile").read_text()

        self.assertRegex(
            dockerfile,
            r"USER dev[\s\S]+RUN curl -fsSL https://opencode.ai/install",
        )
        self.assertIn("/home/dev/.opencode/bin", dockerfile)
        self.assertNotIn("opencode-home", dockerfile)
        self.assertNotIn("/usr/local/bin/opencode", dockerfile)
        self.assertIn('/usr/local/share/devbox/bin/opencode', dockerfile)

    def test_dockerfile_defines_opencode_aliases(self):
        dockerfile = (Path(__file__).parents[1] / "Dockerfile").read_text()
        devboxrc = (Path(__file__).parents[1] / "home" / ".devboxrc").read_text()
        installer = (Path(__file__).parents[1] / "bin" / "devbox-install-user-files").read_text()

        self.assertNotIn("/etc/bash.bashrc", dockerfile)
        self.assertIn("COPY home/.devboxrc", dockerfile)
        self.assertIn("alias oc='command opencode'", devboxrc)
        self.assertIn('source "$SDKMAN_DIR/bin/sdkman-init.sh"', devboxrc)
        self.assertIn("grep -Fqx", installer)
        self.assertIn('source "$HOME/.devboxrc"', installer)

    def test_update_all_attempts_official_opencode_update(self):
        script = (Path(__file__).parents[1] / "bin" / "update-all").read_text()

        self.assertIn("opencode upgrade --method curl", script)
        self.assertIn("https://opencode.ai/install", script)
        self.assertIn("sudo apt update && sudo apt upgrade -y", script)
        self.assertIn('run_update "SDKMAN candidate metadata" sdk update', script)
        self.assertIn('run_update "SDKMAN-managed tools" sdk upgrade', script)
        self.assertIn("https://github.com/coursier/launchers/raw/master/coursier", script)
        self.assertIn('run_update "Coursier" update_coursier', script)
        self.assertIn('run_update "Coursier-managed applications" cs update', script)

    def test_update_all_supports_nounset_unsafe_sdkman_ci_installation(self):
        update_all = Path(__file__).parents[1] / "bin" / "update-all"

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            sdkman_bin = root / "sdkman" / "bin"
            command_bin = root / "bin"
            sdkman_bin.mkdir(parents=True)
            command_bin.mkdir()
            sdk_call_log = root / "sdk-calls"

            (sdkman_bin / "sdkman-init.sh").write_text(
                ': "${ZSH_VERSION}"\n'
                "sdkman_selfupdate_feature=false\n"
                'sdk() { printf "%s\\n" "$1" >> "$SDK_CALL_LOG"; : "$2"; }\n'
            )
            for command in ("sudo", "curl", "cs", "opencode"):
                executable = command_bin / command
                executable.write_text("#!/usr/bin/env bash\nexit 0\n")
                executable.chmod(0o755)

            result = subprocess.run(
                ["bash", str(update_all)],
                capture_output=True,
                env={
                    **os.environ,
                    "PATH": f"{command_bin}:{os.environ['PATH']}",
                    "SDK_CALL_LOG": str(sdk_call_log),
                    "SDKMAN_DIR": str(root / "sdkman"),
                },
                text=True,
            )
            sdk_calls = sdk_call_log.read_text().splitlines()

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn("unbound variable", result.stderr)
        self.assertEqual(sdk_calls, ["update", "upgrade"])

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

    def test_normalizes_docker_desktop_mount_sources_on_macos(self):
        normalize = DEVBOX["normalize_container_path"]

        with mock.patch.object(DEVBOX["sys"], "platform", "darwin"):
            self.assertEqual(
                normalize("/host_mnt/Users/alex/Developer"),
                "/Users/alex/Developer",
            )

    def test_preserves_host_mnt_paths_on_linux(self):
        normalize = DEVBOX["normalize_container_path"]

        with mock.patch.object(DEVBOX["sys"], "platform", "linux"):
            self.assertEqual(
                normalize("/host_mnt/Users/alex/Developer"),
                "/host_mnt/Users/alex/Developer",
            )

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

    def test_configured_container_envs_forwards_non_reserved_names_in_source_order(self):
        configured_container_envs = DEVBOX["configured_container_envs"]
        with mock.patch.dict(
            os.environ,
            {
                "DEVBOX_Z_TOKEN": "last",
                "DEVBOX_EMPTY": "",
                "DEVBOX_IMAGE": "ignored",
                "DEVBOX_AGENT_PORT": "ignored",
                "DEVBOX_HOME_VOLUME": "ignored",
                "DEVBOX_HOME_VOLUME_PREFIX": "ignored",
                "DEVBOX_WIREGUARD_CONFIG_PATH": "ignored",
                "DEVBOX_WIREGUARD_CONFIG_STR": "ignored",
                "DEVBOX_WIREGUARD_MTU": "ignored",
                "DEVBOX_NAME": "workspace",
                "DEVBOX_OPENCODE_CONFIG_DIR": "/config",
                "DEVBOX_AUTH_TOKEN": "compatibility-is-gone",
                "OTHER": "ignored",
            },
            clear=True,
        ):
            self.assertEqual(
                configured_container_envs(),
                [
                    ("DEVBOX_AUTH_TOKEN", "AUTH_TOKEN", "compatibility-is-gone"),
                    ("DEVBOX_EMPTY", "EMPTY", ""),
                    ("DEVBOX_NAME", "NAME", "workspace"),
                    ("DEVBOX_OPENCODE_CONFIG_DIR", "OPENCODE_CONFIG_DIR", "/config"),
                    ("DEVBOX_Z_TOKEN", "Z_TOKEN", "last"),
                ],
            )

    def test_configured_container_envs_rejects_invalid_suffix(self):
        configured_container_envs = DEVBOX["configured_container_envs"]

        with mock.patch.dict(os.environ, {"DEVBOX_BAD-NAME": "value"}, clear=True):
            with self.assertRaisesRegex(SystemExit, "DEVBOX_BAD-NAME"):
                configured_container_envs()

    def test_parse_mount_accepts_existing_file_directory_and_ro(self):
        parse_mounts = DEVBOX["parse_mounts"]

        with tempfile.TemporaryDirectory() as temp_dir:
            source_dir = Path(temp_dir) / "source with spaces"
            source_dir.mkdir()
            source_file = source_dir / "config.txt"
            source_file.write_text("config")
            mounts = parse_mounts(
                [
                    f"{source_dir}:/home/dev/data:ro",
                    f"{source_file}:/home/dev/config.txt",
                ]
            )

            self.assertEqual(mounts[0].source, str(source_dir.resolve()))
            self.assertEqual(mounts[1].source, str(source_file.resolve()))

        self.assertEqual(mounts[0].target, "/home/dev/data")
        self.assertEqual(mounts[0].options, "ro")

    def test_parse_mount_handles_windows_drive_paths(self):
        parse_mounts = DEVBOX["parse_mounts"]
        globals_ = parse_mounts.__globals__

        with mock.patch.dict(globals_, {"canonical_mount_source": lambda path: path}):
            mounts = parse_mounts([r"C:\Users\alex:/home/dev/data:ro"])

        self.assertEqual(mounts[0].source, r"C:\Users\alex")
        self.assertEqual(mounts[0].target, "/home/dev/data")
        self.assertEqual(mounts[0].options, "ro")

    def test_parse_mount_rejects_invalid_sources_targets_and_duplicates(self):
        parse_mounts = DEVBOX["parse_mounts"]

        with self.assertRaisesRegex(SystemExit, "source does not exist"):
            parse_mounts(["/not/a/source:/home/dev/data"])
        with tempfile.TemporaryDirectory() as temp_dir:
            with self.assertRaisesRegex(SystemExit, "absolute"):
                parse_mounts([f"{temp_dir}:relative"])
            with self.assertRaisesRegex(SystemExit, "Duplicate mount target"):
                parse_mounts([f"{temp_dir}:/home/dev/data", f"{temp_dir}:/home/dev/data"])


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

    def test_generic_environment_arguments_include_empty_values(self):
        instance = new_devbox()
        globals_ = instance.configure_container_env_args.__globals__

        with mock.patch.dict(
            globals_,
            {
                "configured_container_envs": lambda: [
                    ("DEVBOX_EMPTY", "EMPTY", ""),
                    ("DEVBOX_TOKEN", "TOKEN", "secret"),
                ]
            },
        ):
            instance.configure_container_env_args()

        self.assertEqual(
            instance.container_env_args,
            ["-e", "EMPTY=", "-e", "TOKEN=secret"],
        )

    def test_compose_forwards_variable_references_without_values(self):
        instance = new_devbox("compose")
        globals_ = instance.compose_environment.__globals__

        with mock.patch.dict(
            globals_,
            {
                "configured_container_envs": lambda: [
                    ("DEVBOX_EMPTY", "EMPTY", ""),
                    ("DEVBOX_TOKEN", "TOKEN", "secret"),
                ]
            },
        ), mock.patch("sys.stdout", new_callable=io.StringIO) as stdout:
            instance.compose_environment()

        output = stdout.getvalue()
        self.assertIn('EMPTY: "${DEVBOX_EMPTY}"', output)
        self.assertIn('TOKEN: "${DEVBOX_TOKEN}"', output)
        self.assertNotIn("secret", output)

    def test_compose_prints_structured_custom_mount_with_read_only(self):
        mount = DEVBOX["Mount"]("/host data:/home/dev/data:ro", "/host data", "/home/dev/data", "ro")
        instance = new_devbox("compose")
        instance.mounts = [mount]

        with mock.patch("sys.stdout", new_callable=io.StringIO) as stdout:
            instance.compose_mounts()

        output = stdout.getvalue()
        self.assertIn('source: "/host data"', output)
        self.assertIn('target: "/home/dev/data"', output)
        self.assertIn("read_only: true", output)

    def test_compose_represent_explicit_read_write_mount(self):
        mount = DEVBOX["Mount"]("/host:/home/dev/data:rw", "/host", "/home/dev/data", "rw")
        instance = new_devbox("compose")
        instance.mounts = [mount]

        with mock.patch("sys.stdout", new_callable=io.StringIO) as stdout:
            instance.compose_mounts()

        self.assertNotIn("read_only", stdout.getvalue())

    def test_compose_rejects_mount_options_it_cannot_represent(self):
        mount = DEVBOX["Mount"]("/host:/home/dev/data:z", "/host", "/home/dev/data", "z")
        instance = new_devbox("compose")
        instance.mounts = [mount]

        with mock.patch("sys.stdout", new_callable=io.StringIO):
            with self.assertRaisesRegex(SystemExit, "cannot be represented in Compose"):
                instance.compose_mounts()

    def test_compose_mounts_include_custom_mount_label(self):
        instance = new_devbox("compose")
        instance.mounts = [DEVBOX["Mount"]("/host:/data", "/host", "/data", "")]

        with mock.patch("sys.stdout", new_callable=io.StringIO) as stdout:
            instance.compose_service()

        self.assertIn(DEVBOX["MOUNTS_LABEL"], stdout.getvalue())

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

        with mock.patch.dict(os.environ, {"DEVBOX_WIREGUARD_CONFIG_PATH": "~/wg.conf"}, clear=True), mock.patch.dict(
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
                "--add-host",
                "host.docker.internal:host-gateway",
                "-v",
                "/home/alex/wg.conf:/etc/wireguard/devbox.conf:ro",
                "-e",
                "DEVBOX_WIREGUARD_MTU=1420",
            ],
        )
        self.assertTrue(
            instance.workspace_link_command().startswith(
                'HOST_DOCKER_INTERNAL_IP="$(getent ahostsv4 host.docker.internal '
            )
        )
        command = instance.workspace_link_command()
        self.assertIn('ip -4 route get "$HOST_DOCKER_INTERNAL_IP"', command)
        self.assertIn('ip -4 route replace table main "$HOST_DOCKER_INTERNAL_IP/32"', command)
        self.assertLess(command.index("ip -4 route replace"), command.index("wg-quick up"))

    def test_wireguard_string_configuration_is_forwarded_without_mount(self):
        instance = new_devbox(container_cli="podman")
        config = "[Interface]\nPrivateKey = secret\n"

        with mock.patch.dict(os.environ, {"DEVBOX_WIREGUARD_CONFIG_STR": config}, clear=True):
            instance.configure_wireguard()

        self.assertEqual(instance.wireguard_config_str, config)
        self.assertNotIn("-v", instance.wireguard_args())
        self.assertEqual(
            instance.wireguard_args(),
            [
                "--cap-add",
                "NET_ADMIN",
                "--sysctl",
                "net.ipv4.conf.all.src_valid_mark=1",
                "--add-host",
                "host.docker.internal:host-gateway",
                "-e",
                f"DEVBOX_WIREGUARD_CONFIG_STR={config}",
                "-e",
                "DEVBOX_WIREGUARD_MTU=1420",
            ],
        )
        command = instance.workspace_link_command()
        self.assertIn('printf \'%s\' "$DEVBOX_WIREGUARD_CONFIG_STR" > /etc/wireguard/devbox.conf', command)
        self.assertLess(command.index("printf"), command.index("wg-quick"))

    def test_wireguard_compose_maps_the_docker_host(self):
        instance = new_devbox("compose", container_cli="docker")
        instance.wireguard_config_host_path = "/wg.conf"
        instance.wireguard_mtu = "1420"

        with mock.patch("sys.stdout", new_callable=io.StringIO) as stdout:
            instance.compose_service()

        self.assertIn(
            '    extra_hosts:\n      - "host.docker.internal:host-gateway"\n',
            stdout.getvalue(),
        )

    def test_wireguard_rejects_path_and_string_configuration_together(self):
        instance = new_devbox(container_cli="podman")

        with mock.patch.dict(
            os.environ,
            {
                "DEVBOX_WIREGUARD_CONFIG_PATH": "/wg.conf",
                "DEVBOX_WIREGUARD_CONFIG_STR": "[Interface]",
            },
            clear=True,
        ):
            with self.assertRaisesRegex(SystemExit, "DEVBOX_WIREGUARD_CONFIG_PATH.*DEVBOX_WIREGUARD_CONFIG_STR"):
                instance.configure_wireguard()

    def test_wireguard_rejects_invalid_mtu(self):
        instance = new_devbox(container_cli="podman")
        globals_ = instance.configure_wireguard.__globals__

        with mock.patch.dict(
            os.environ,
            {"DEVBOX_WIREGUARD_CONFIG_PATH": "/wg.conf", "DEVBOX_WIREGUARD_MTU": "huge"},
            clear=True,
        ), mock.patch.dict(globals_, {"canonical_file": lambda _path, _description: "/wg.conf"}):
            with self.assertRaisesRegex(SystemExit, "DEVBOX_WIREGUARD_MTU"):
                instance.configure_wireguard()

    def test_wireguard_fails_early_with_explanation_on_wslc(self):
        instance = new_devbox(container_cli="wslc.exe")
        globals_ = instance.configure_wireguard.__globals__

        with mock.patch.dict(os.environ, {"DEVBOX_WIREGUARD_CONFIG_PATH": "/wg.conf"}, clear=True), mock.patch.dict(
            globals_, {"canonical_file": lambda _path, _description: "/wg.conf"}
        ):
            with self.assertRaisesRegex(SystemExit, "wslc.*NET_ADMIN"):
                instance.configure_wireguard()

    def test_help_env_documents_optional_wireguard_configuration(self):
        help_text = DEVBOX["ENVIRONMENT_HELP"]

        self.assertIn("DEVBOX_WIREGUARD_CONFIG_PATH", help_text)
        self.assertIn("DEVBOX_WIREGUARD_CONFIG_STR", help_text)
        self.assertNotIn("DEVBOX_WIREGUARD_CONFIG ", help_text)
        self.assertIn("DEVBOX_WIREGUARD_MTU", help_text)
        self.assertIn("optional", help_text.lower())

    def test_entrypoint_writes_wireguard_string_configuration(self):
        entrypoint = (Path(__file__).parents[1] / "bin" / "devbox-entrypoint").read_text()

        self.assertIn('printf \'%s\' "$DEVBOX_WIREGUARD_CONFIG_STR"', entrypoint)
        self.assertIn("/etc/wireguard/devbox.conf", entrypoint)
        self.assertNotIn("OPENCODE_CONFIG_DIR", entrypoint)


class ContainerExecutionTest(unittest.TestCase):
    def test_custom_mounts_add_canonical_label_and_runtime_volume_arguments(self):
        mount = DEVBOX["Mount"]("/host:/home/dev/data:ro", "/host", "/home/dev/data", "ro")
        instance = new_devbox(container_cli="docker")
        instance.project_mount_dir = "/project"
        instance.project_container_mount_dir = "/project"
        instance.project_container_dir = "/project"
        instance.mounts = [mount]

        with mock.patch.object(instance, "run_cli") as run_cli:
            instance.run_new_container()

        command = run_cli.call_args.args[0]
        self.assertIn(f'{DEVBOX["MOUNTS_LABEL"]}={instance.mount_label()}', command)
        self.assertIn("/host:/home/dev/data:ro", command)

    def test_custom_mount_label_accepts_equal_and_legacy_empty_configuration(self):
        mount = DEVBOX["Mount"]("/host:/home/dev/data", "/host", "/home/dev/data", "")
        other_mount = DEVBOX["Mount"]("/other:/home/dev/other", "/other", "/home/dev/other", "ro")
        instance = new_devbox(container_cli="docker")
        instance.mounts = [mount, other_mount]
        container = {"Config": {"Labels": {DEVBOX["MOUNTS_LABEL"]: instance.mount_label()}}}

        with mock.patch.object(instance, "container_inspect", return_value=container):
            instance.ensure_custom_mounts()

        instance.mounts.reverse()
        with mock.patch.object(instance, "container_inspect", return_value=container):
            instance.ensure_custom_mounts()

        instance.mounts = []
        with mock.patch.object(instance, "container_inspect", return_value={"Config": {"Labels": {}}}):
            instance.ensure_custom_mounts()

    def test_custom_mount_label_mismatch_requires_purge(self):
        mount = DEVBOX["Mount"]("/host:/home/dev/data", "/host", "/home/dev/data", "")
        instance = new_devbox(container_cli="docker")
        instance.mounts = [mount]

        with mock.patch.object(
            instance,
            "container_inspect",
            return_value={"Config": {"Labels": {DEVBOX["MOUNTS_LABEL"]: "[]"}}},
        ), mock.patch("sys.stderr", new_callable=io.StringIO) as stderr:
            with self.assertRaisesRegex(SystemExit, "1"):
                instance.ensure_custom_mounts()

        self.assertIn("purge", stderr.getvalue())

    def test_project_mount_accepts_docker_desktop_macos_source(self):
        instance = new_devbox(container_cli="docker")
        instance.project_mount_dir = "/Users/alex/Developer"
        instance.project_container_mount_dir = "/Users/alex/Developer"
        instance.project_container_dir = "/Users/alex/Developer"
        container = {
            "Config": {"WorkingDir": "/Users/alex/Developer"},
            "Mounts": [
                {
                    "Source": "/host_mnt/Users/alex/Developer",
                    "Destination": "/Users/alex/Developer",
                },
            ],
        }

        with mock.patch.object(DEVBOX["sys"], "platform", "darwin"), mock.patch.object(
            DEVBOX["os"].path, "realpath", side_effect=lambda path: path
        ), mock.patch.object(instance, "container_inspect", return_value=container):
            instance.ensure_project_mount()

    def test_project_mount_mismatch_reports_running_and_current_configuration(self):
        instance = new_devbox(container_cli="docker")
        instance.project_mount_dir = "/current/workspace"
        instance.project_container_mount_dir = "/current/workspace"
        instance.project_container_dir = "/current/workspace/project"
        container = {
            "Config": {"WorkingDir": "/running/workspace/project"},
            "Mounts": [
                {"Source": "/running/workspace", "Destination": "/running/workspace"},
            ],
        }

        with mock.patch.object(instance, "container_inspect", return_value=container), mock.patch(
            "sys.stderr", new_callable=io.StringIO
        ) as stderr:
            with self.assertRaisesRegex(SystemExit, "1"):
                instance.ensure_project_mount()

        output = stderr.getvalue()
        for expected in (
            "Running container configuration:",
            "Project: /running/workspace -> /running/workspace",
            "Workdir: /running/workspace/project",
            "Current configuration:",
            "Project: /current/workspace -> /current/workspace",
            "Workdir: /current/workspace/project",
        ):
            self.assertIn(expected, output)

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


class StatusTest(unittest.TestCase):
    def test_status_reports_missing_container(self):
        instance = new_devbox("status", container_cli="wslc.exe")

        with mock.patch.object(instance, "container_inspect", return_value={}), mock.patch(
            "sys.stdout", new_callable=io.StringIO
        ) as stdout:
            instance.status_container()

        self.assertIn("Runtime:   wslc.exe", stdout.getvalue())
        self.assertIn("Status:    not created", stdout.getvalue())

    def test_status_reports_running_container_runtime_configuration(self):
        instance = new_devbox("status", container_cli="podman")
        container = {
            "Id": "abcdef1234567890",
            "Created": "2026-07-12T10:00:00Z",
            "Config": {
                "Image": "devbox:test",
                "WorkingDir": "/workspace/project",
                "Env": ["DEVBOX_WIREGUARD_MTU=1420", "SECRET=hidden"],
            },
            "State": {"Running": True, "Status": "running", "StartedAt": "2026-07-12T10:00:01Z"},
            "Mounts": [
                {"Source": "/host/project", "Destination": "/workspace/project", "RW": True},
                {"Name": "devbox-home", "Destination": "/home/dev", "RW": True},
                {"Source": "/host/wg.conf", "Destination": "/etc/wireguard/devbox.conf", "RW": False},
            ],
            "HostConfig": {"PortBindings": {"10012/tcp": [{"HostPort": "10012"}]}},
        }

        with mock.patch.object(instance, "container_inspect", return_value=container), mock.patch.object(
            instance, "container_wireguard_status", return_value="active; latest handshake 30 seconds ago"
        ), mock.patch("sys.stdout", new_callable=io.StringIO) as stdout:
            instance.status_container()

        output = stdout.getvalue()
        for expected in (
            "Runtime:   podman",
            "Status:    running",
            "Image:     devbox:test",
            "ID:        abcdef123456",
            "Workdir:   /workspace/project",
            "/host/project -> /workspace/project (rw)",
            "devbox-home -> /home/dev (rw)",
            "Agent:     localhost:10012 -> 10012/tcp",
            "WireGuard: enabled; config=/host/wg.conf; MTU=1420",
            "Tunnel:    active; latest handshake 30 seconds ago",
        ):
            self.assertIn(expected, output)
        self.assertNotIn("SECRET", output)

    def test_status_reports_exit_details(self):
        instance = new_devbox("status", container_cli="podman")
        container = {
            "Config": {"Image": "devbox:test", "WorkingDir": "/workspace"},
            "State": {"Running": False, "Status": "exited", "ExitCode": 127, "FinishedAt": "today"},
        }

        with mock.patch.object(instance, "container_inspect", return_value=container), mock.patch(
            "sys.stdout", new_callable=io.StringIO
        ) as stdout:
            instance.status_container()

        self.assertIn("Status:    exited (exit code 127)", stdout.getvalue())
        self.assertIn("Finished:  today", stdout.getvalue())


class ParserTest(unittest.TestCase):
    def test_status_parses_without_arguments(self):
        namespace = DEVBOX["build_parser"]().parse_args(["status"])

        self.assertEqual(namespace.command, "status")

    def test_start_requires_and_parses_project_directory(self):
        namespace = DEVBOX["build_parser"]().parse_args(["start", "."])

        self.assertEqual(namespace.command, "start")
        self.assertEqual(namespace.project_directory, ".")

    def test_start_and_compose_parse_repeated_mount_options(self):
        parser = DEVBOX["build_parser"]()

        for command in ("start", "compose"):
            with self.subTest(command=command):
                namespace = parser.parse_args(
                    [command, "--mount", "/one:/home/dev/one", "--mount", "/two:/home/dev/two:ro", "."]
                )
                self.assertEqual(namespace.mounts, ["/one:/home/dev/one", "/two:/home/dev/two:ro"])

    def test_exec_preserves_passthrough_arguments(self):
        namespace = DEVBOX["build_parser"]().parse_args(["exec", "python", "-c", "print('ok')"])

        self.assertEqual(namespace.command_args, ["python", "-c", "print('ok')"])


if __name__ == "__main__":
    unittest.main()
