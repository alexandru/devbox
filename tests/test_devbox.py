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

        with mock.patch.dict(devbox_class.__init__.__globals__, {"workspace_mount_path": lambda _path: r"C:\Users"}):
            instance = devbox_class("start", workspace_dir=r"C:\Users\alex")

        self.assertEqual(instance.workspace_mount_dir, r"C:\Users")
        self.assertEqual(instance.workspace_container_mount_dir, "/c/Users")
        self.assertEqual(instance.workspace_container_dir, "/c/Users/alex")


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

    def test_dockerfile_installs_bubblewrap(self):
        dockerfile = (Path(__file__).parents[1] / "Dockerfile").read_text()

        self.assertIn("bubblewrap", dockerfile)

    def test_dockerfile_installs_htop(self):
        dockerfile = (Path(__file__).parents[1] / "Dockerfile").read_text()

        self.assertIn("htop", dockerfile)

    def test_dockerfile_installs_tmux(self):
        dockerfile = (Path(__file__).parents[1] / "Dockerfile").read_text()

        self.assertIn("tmux", dockerfile)

    def test_dockerfile_configures_utf8_locale_environment(self):
        dockerfile = (Path(__file__).parents[1] / "Dockerfile").read_text()

        self.assertIn("ENV LANG=C.UTF-8", dockerfile)
        self.assertIn("ENV LC_CTYPE=C.UTF-8", dockerfile)

    def test_image_has_gateway_ssh_server_dependencies_and_configuration(self):
        root = Path(__file__).parents[1]
        dockerfile = (root / "Dockerfile").read_text()
        sshd_config = (root / "etc" / "ssh" / "sshd_config.d" / "devbox.conf").read_text()

        for package in (
            "openssh-server",
            "libfreetype6",
            "libxext6",
            "libxi6",
            "libxrender1",
            "libxtst6",
        ):
            with self.subTest(package=package):
                self.assertIn(package, dockerfile)
        self.assertIn("COPY etc/ssh/sshd_config.d/devbox.conf", dockerfile)
        self.assertIn("COPY bin/devbox-start-sshd", dockerfile)
        self.assertIn("AuthenticationMethods publickey", sshd_config)
        self.assertIn("AuthorizedKeysFile .ssh/authorized_keys", sshd_config)
        self.assertIn("AllowTcpForwarding yes", sshd_config)
        self.assertIn("PermitRootLogin no", sshd_config)

    def test_dockerfile_installs_github_cli_from_official_repository(self):
        dockerfile = (Path(__file__).parents[1] / "Dockerfile").read_text()

        self.assertIn("https://cli.github.com/packages/githubcli-archive-keyring.gpg", dockerfile)
        self.assertIn("https://cli.github.com/packages stable main", dockerfile)
        self.assertIn("apt-get install -y --no-install-recommends gh", dockerfile)

    def test_agent_clis_are_not_bundled_or_updated(self):
        root = Path(__file__).parents[1]
        dockerfile = (root / "Dockerfile").read_text()
        update_all = (root / "bin" / "update-all").read_text()
        installer = (root / "bin" / "devbox-install-user-files").read_text()
        devboxrc = (root / "home" / ".devboxrc").read_text()
        readme = (root / "README.md").read_text()

        for content in (dockerfile, update_all, installer, devboxrc, readme):
            for unwanted in (
                "opencode",
                "@earendil-works/pi-coding-agent",
                "@github/copilot",
                "@openai/codex",
                "OpenCode",
                "Copilot CLI",
                "Codex CLI",
                "\n- Pi\n",
            ):
                with self.subTest(unwanted=unwanted):
                    self.assertNotIn(unwanted, content)

    def test_readme_documents_workspace_native_volume_and_exec_usage(self):
        readme = (Path(__file__).parents[1] / "README.md").read_text()

        for example in (
            "devbox start --workspace",
            "devbox start --volume",
            "devbox shell",
            "devbox exec --workdir",
            "docker volume create devbox-projects",
            "devbox compose --volume",
        ):
            with self.subTest(example=example):
                self.assertIn(example, readme)

    def test_readme_documents_intellij_remote_development(self):
        readme = (Path(__file__).parents[1] / "README.md").read_text()

        for expected in (
            "--ssh-port 2222",
            "/home/dev/.ssh/authorized_keys",
            "Remote Development",
            "dev@localhost:2222",
        ):
            with self.subTest(expected=expected):
                self.assertIn(expected, readme)

    def test_start_help_explains_opt_in_testcontainers_support(self):
        with mock.patch("sys.stdout", new_callable=io.StringIO) as stdout:
            with self.assertRaisesRegex(SystemExit, "0"):
                DEVBOX["main"](["start", "--help"])

        help_text = stdout.getvalue()
        self.assertIn("--container-socket", help_text)
        self.assertIn("Testcontainers", help_text)
        self.assertIn("root-equivalent control", help_text)
        self.assertIn("Rootless Podman", help_text)
        self.assertIn("wslc", help_text)

    def test_start_help_explains_remote_ide_ssh_authentication(self):
        with mock.patch("sys.stdout", new_callable=io.StringIO) as stdout:
            with self.assertRaisesRegex(SystemExit, "0"):
                DEVBOX["main"](["start", "--help"])

        help_text = stdout.getvalue()
        self.assertIn("--ssh-port", help_text)
        self.assertIn("/home/dev/.ssh/authorized_keys", help_text)
        self.assertIn("key-only", help_text)
        self.assertIn("127.0.0.1", help_text)

    def test_dockerfile_disables_cellar_telemetry_as_dev_user(self):
        dockerfile = (Path(__file__).parents[1] / "Dockerfile").read_text()

        self.assertRegex(
            dockerfile,
            r"USER dev[\s\S]+RUN cs install --contrib cellar && \\\n+    cellar telemetry disable",
        )

    def test_dockerfile_installs_devboxrc(self):
        dockerfile = (Path(__file__).parents[1] / "Dockerfile").read_text()
        devboxrc = (Path(__file__).parents[1] / "home" / ".devboxrc").read_text()
        installer = (Path(__file__).parents[1] / "bin" / "devbox-install-user-files").read_text()

        self.assertNotIn("/etc/bash.bashrc", dockerfile)
        self.assertIn("COPY home/.devboxrc", dockerfile)
        self.assertIn('source "$SDKMAN_DIR/bin/sdkman-init.sh"', devboxrc)
        self.assertIn("grep -Fqx", installer)
        self.assertIn('source "$HOME/.devboxrc"', installer)

    def test_update_all_keeps_system_and_jvm_tools_current(self):
        script = (Path(__file__).parents[1] / "bin" / "update-all").read_text()

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
            for command in ("sudo", "curl", "cs"):
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

    def test_parse_named_volumes_normalizes_home_paths_and_options(self):
        parse_named_volumes = DEVBOX["parse_named_volumes"]

        volumes = parse_named_volumes(["projects:~/projects", "cache:~/cache:ro", "build:/var/build:rw"])

        self.assertEqual(
            [(volume.source, volume.target, volume.options) for volume in volumes],
            [("projects", "/home/dev/projects", ""), ("cache", "/home/dev/cache", "ro"), ("build", "/var/build", "rw")],
        )

    def test_parse_named_volumes_rejects_reserved_names_and_target_collisions(self):
        parse_named_volumes = DEVBOX["parse_named_volumes"]
        mount = DEVBOX["Mount"]("/host:/data", "/host", "/data", "")

        for specification in ("devbox-home:/data", "devbox-home-old:/data", "projects:/home/dev", "projects:relative", "projects:/data:z"):
            with self.subTest(specification=specification), self.assertRaisesRegex(SystemExit, "(?:reserved|home/dev|absolute|options)"):
                parse_named_volumes([specification], [mount])

        with self.assertRaisesRegex(SystemExit, "Duplicate mount target"):
            parse_named_volumes(["projects:/data"], [mount])


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
        instance = new_devbox(workspace_dir="/project")
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
        instance = new_devbox(workspace_dir=r"C:\Users\alex")
        globals_ = instance.container_directory.__globals__

        with mock.patch.object(instance, "container_workspace_mount", return_value=("/project", "/project")), mock.patch.dict(
            globals_, {"canonical_dir": lambda _path, _description: "/elsewhere"}
        ), mock.patch("sys.stderr", new_callable=io.StringIO) as stderr:
            with self.assertRaisesRegex(SystemExit, "1"):
                instance.container_directory("/elsewhere")

        self.assertIn("outside the started workspace", stderr.getvalue())

    def test_container_directory_converts_windows_relative_separators(self):
        instance = new_devbox(workspace_dir="/home/alex")
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
        instance = new_devbox(workspace_dir="/home/alex")
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

    def test_ssh_port_rejects_the_agent_host_port(self):
        instance = new_devbox("start")
        instance.ssh_port = "10012"

        with mock.patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(SystemExit, "SSH host port.*agent host port"):
                instance.configure_agent_port()

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

    def test_compose_does_not_forward_ssh_auth_sock(self):
        instance = new_devbox("compose")

        with mock.patch.dict(os.environ, {"SSH_AUTH_SOCK": "/tmp/test-agent.sock"}, clear=True), mock.patch(
            "sys.stdout", new_callable=io.StringIO
        ) as stdout:
            instance.compose_environment()
            instance.compose_mounts()

        self.assertNotIn("SSH_AUTH_SOCK", stdout.getvalue())
        self.assertNotIn("/tmp/test-agent.sock", stdout.getvalue())

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

    def test_compose_native_mode_omits_workspace_bind_and_declares_external_volume(self):
        instance = new_devbox("compose")
        instance.mode = "container-native"
        instance.named_volumes = [
            DEVBOX["Mount"]("projects:~/projects:ro", "projects", "/home/dev/projects", "ro", "volume")
        ]

        with mock.patch("sys.stdout", new_callable=io.StringIO) as stdout:
            instance.compose_file()

        output = stdout.getvalue()
        self.assertNotIn('source: ""', output)
        self.assertIn("type: volume", output)
        self.assertIn("target: \"/home/dev/projects\"", output)
        self.assertIn("read_only: true", output)
        key = instance.compose_volume_key("projects")
        self.assertIn(f"source: \"{key}\"", output)
        self.assertIn(f"  {key}:\n    name: \"projects\"\n    external: true", output)
        self.assertIn('org.alexn.devbox: "true"', output)
        self.assertNotIn('org.alexn.devbox: "true"', output[output.index(f"  {key}:"):])

    def test_compose_exposes_configured_container_socket(self):
        instance = new_devbox("compose", container_cli="docker")
        instance.container_socket = "/var/run/docker.sock"
        instance.container_socket_gid = 998

        with mock.patch("sys.stdout", new_callable=io.StringIO) as stdout:
            instance.compose_service()

        output = stdout.getvalue()
        self.assertIn('DOCKER_HOST: "unix:///var/run/docker.sock"', output)
        self.assertIn('TESTCONTAINERS_DOCKER_SOCKET_OVERRIDE: "/var/run/docker.sock"', output)
        self.assertIn('group_add:\n      - "998"', output)
        self.assertIn('source: "/var/run/docker.sock"', output)
        self.assertIn('target: "/var/run/docker.sock"', output)

    def test_compose_workspace_mode_uses_workspace_workdir_and_bind(self):
        instance = new_devbox("compose", workspace_dir="/host/workspace")
        instance.workspace_mount_dir = "/host"
        instance.workspace_container_mount_dir = "/workspace"
        instance.workspace_container_dir = "/workspace/workspace"

        with mock.patch("sys.stdout", new_callable=io.StringIO) as stdout:
            instance.compose_service()

        output = stdout.getvalue()
        self.assertIn('working_dir: "/workspace/workspace"', output)
        self.assertIn('source: "/host"', output)
        self.assertIn('target: "/workspace"', output)

    def test_compose_publishes_ssh_on_loopback_and_starts_the_server(self):
        instance = new_devbox("compose")
        instance.ssh_port = "2222"

        with mock.patch("sys.stdout", new_callable=io.StringIO) as stdout:
            instance.compose_service()

        output = stdout.getvalue()
        self.assertIn('      - "127.0.0.1:2222:22"', output)
        self.assertIn('org.alexn.devbox.ssh-port: "2222"', output)
        self.assertIn("devbox-start-sshd", output)

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

    def test_nested_sandbox_compose_configuration(self):
        instance = new_devbox("compose", container_cli="docker")
        instance.nested_sandbox = True

        with mock.patch("sys.stdout", new_callable=io.StringIO) as stdout:
            instance.compose_service()

        output = stdout.getvalue()
        for capability in ("SYS_ADMIN", "SYS_CHROOT", "SETUID", "SETGID", "SYS_PTRACE"):
            self.assertIn(f"      - {capability}", output)
        self.assertIn("    security_opt:\n      - seccomp=unconfined\n      - apparmor=unconfined", output)

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

    def test_nested_sandbox_fails_early_with_explanation_on_wslc(self):
        instance = new_devbox(container_cli="wslc.exe")
        instance.nested_sandbox = True

        with self.assertRaisesRegex(SystemExit, "Nested sandbox.*wslc"):
            instance.configure_nested_sandbox()

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
    def test_run_new_container_does_not_mount_ssh_auth_sock(self):
        instance = new_devbox("start", container_cli="docker")

        with mock.patch.dict(os.environ, {"SSH_AUTH_SOCK": "/tmp/test-agent.sock"}, clear=True), mock.patch.object(
            instance, "run_cli"
        ) as run_cli:
            instance.run_new_container()

        command = run_cli.call_args.args[0]
        self.assertNotIn("/tmp/test-agent.sock", " ".join(command))
        self.assertNotIn("SSH_AUTH_SOCK", " ".join(command))

    def test_ssh_port_publishes_on_loopback_and_starts_the_server(self):
        instance = new_devbox("start", container_cli="docker")
        instance.ssh_port = "2222"

        with mock.patch.object(instance, "run_cli") as run_cli:
            instance.run_new_container()

        command = run_cli.call_args.args[0]
        self.assertIn("127.0.0.1:2222:22", command)
        self.assertIn("org.alexn.devbox.ssh-port=2222", command)
        self.assertIn("devbox-start-sshd && exec sleep infinity", command[-1])

    def test_docker_container_socket_adds_mount_environment_and_socket_group(self):
        instance = new_devbox("start", container_cli="docker")
        instance.container_socket_request = "/var/run/docker.sock"

        with mock.patch.object(DEVBOX["os"].path, "exists", return_value=True), mock.patch.object(
            DEVBOX["os"], "stat", return_value=mock.Mock(st_gid=998)
        ):
            instance.configure_container_socket()

        with mock.patch.object(instance, "run_cli") as run_cli:
            instance.run_new_container()

        command = run_cli.call_args.args[0]
        self.assertIn(f"{os.path.realpath('/var/run/docker.sock')}:/var/run/docker.sock", command)
        self.assertIn("DOCKER_HOST=unix:///var/run/docker.sock", command)
        self.assertIn("TESTCONTAINERS_DOCKER_SOCKET_OVERRIDE=/var/run/docker.sock", command)
        self.assertEqual(command[command.index("--group-add") + 1], "998")

    def test_rootless_podman_socket_uses_docker_api_compatibility_settings(self):
        instance = new_devbox("start", container_cli="podman")
        instance.container_socket_request = "auto"

        with mock.patch.dict(
            os.environ,
            {"DEVBOX_CONTAINER_SOCKET": "/run/user/1000/podman/podman.sock"},
            clear=True,
        ), mock.patch.object(DEVBOX["os"].path, "exists", return_value=True), mock.patch.object(
            DEVBOX["os"], "stat", return_value=mock.Mock(st_gid=1000)
        ):
            instance.configure_container_socket()

        with mock.patch.object(instance, "run_cli") as run_cli:
            instance.run_new_container()

        command = run_cli.call_args.args[0]
        self.assertIn("/run/user/1000/podman/podman.sock:/var/run/docker.sock", command)
        self.assertIn("TESTCONTAINERS_RYUK_DISABLED=true", command)
        self.assertIn("label=disable", command)

    def test_container_socket_fails_early_with_explanation_on_wslc(self):
        instance = new_devbox("start", container_cli="wslc.exe")
        instance.container_socket_request = "auto"

        with self.assertRaisesRegex(SystemExit, "Container socket.*wslc"):
            instance.configure_container_socket()

    def test_container_native_paths_resolve_without_host_preflight(self):
        instance = new_devbox("exec", execution_dir="~/projects", container_cli="docker")
        instance.mode = "container-native"

        with mock.patch.object(DEVBOX["os"].path, "isdir", side_effect=AssertionError("host preflight")):
            self.assertEqual(instance.container_directory("~/projects/../src"), "/home/dev/src")
            self.assertEqual(instance.container_directory("./cache"), "/home/dev/cache")
            self.assertEqual(instance.container_directory("/tmp/../var"), "/var")

    def test_native_container_run_omits_workspace_bind_and_symlink(self):
        instance = new_devbox("start", container_cli="docker")
        instance.mode = "container-native"

        with mock.patch.object(instance, "run_cli") as run_cli:
            instance.run_new_container()

        command = run_cli.call_args.args[0]
        self.assertNotIn("/workspace", command)
        self.assertNotIn("ln -s", command)
        self.assertIn("-w", command)
        self.assertEqual(command[command.index("-w") + 1], "/home/dev")

    def test_named_volume_runtime_mount_and_initialization(self):
        instance = new_devbox("start", container_cli="docker")
        instance.mode = "container-native"
        instance.named_volumes = [
            DEVBOX["Mount"]("projects:~/projects", "projects", "/home/dev/projects", "", "volume"),
            DEVBOX["Mount"]("cache:~/cache:ro", "cache", "/home/dev/cache", "ro", "volume"),
        ]

        with mock.patch.object(instance, "run_cli") as run_cli:
            instance.run_new_container()

        command = run_cli.call_args.args[0]
        self.assertIn("projects:/home/dev/projects", command)
        startup = command[-1]
        self.assertIn("find /home/dev/projects -mindepth 1 -maxdepth 1", startup)
        self.assertIn("chown dev:dev /home/dev/projects", startup)
        self.assertIn("cache:/home/dev/cache:ro", command)
        self.assertNotIn("/home/dev/cache", startup)
        self.assertNotIn("chown -R", startup)

    def test_workspace_runtime_records_mode_and_requested_workspace_labels(self):
        instance = new_devbox("start", workspace_dir="/host/workspace", container_cli="docker")
        instance.workspace_mount_dir = "/host"
        instance.workspace_container_mount_dir = "/workspace"
        instance.workspace_container_dir = "/workspace/workspace"

        with mock.patch.object(instance, "run_cli") as run_cli:
            instance.run_new_container()

        command = run_cli.call_args.args[0]
        self.assertIn(f"{DEVBOX['MODE_LABEL']}=workspace", command)
        self.assertIn(f"{DEVBOX['WORKSPACE_LABEL']}=/host/workspace", command)
        self.assertIn("/host:/workspace", command)
        self.assertIn("-w", command)
        self.assertEqual(command[command.index("-w") + 1], "/workspace/workspace")

    def test_custom_mounts_add_canonical_label_and_runtime_volume_arguments(self):
        mount = DEVBOX["Mount"]("/host:/home/dev/data:ro", "/host", "/home/dev/data", "ro")
        instance = new_devbox(container_cli="docker")
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

    def test_named_volume_label_mismatch_requires_purge(self):
        instance = new_devbox("start", container_cli="docker")
        instance.named_volumes = [
            DEVBOX["Mount"]("projects:~/projects", "projects", "/home/dev/projects", "", "volume")
        ]
        container = {
            "Config": {
                "WorkingDir": "/home/dev",
                "Labels": {DEVBOX["MOUNTS_LABEL"]: "[]"},
            },
            "Mounts": [{"Name": "devbox-home", "Destination": "/home/dev"}],
        }

        with mock.patch.object(instance, "container_exists", return_value=True), mock.patch.object(
            instance, "container_inspect", return_value=container
        ), mock.patch("sys.stderr", new_callable=io.StringIO) as stderr:
            with self.assertRaisesRegex(SystemExit, "1"):
                instance.start_container(announce=False)

        self.assertIn("purge", stderr.getvalue())

    def test_reusing_container_from_other_mode_requires_purge(self):
        instance = new_devbox("start", workspace_dir="/host/workspace", container_cli="docker")
        container = {
            "Config": {
                "WorkingDir": "/home/dev",
                "Labels": {DEVBOX["MODE_LABEL"]: "container-native"},
            },
            "Mounts": [{"Name": "devbox-home", "Destination": "/home/dev"}],
        }

        with mock.patch.object(instance, "container_exists", return_value=True), mock.patch.object(
            instance, "container_inspect", return_value=container
        ), mock.patch(
            "sys.stderr", new_callable=io.StringIO
        ) as stderr:
            with self.assertRaisesRegex(SystemExit, "1"):
                instance.start_container(announce=False)

        self.assertIn("purge", stderr.getvalue())

    def test_nested_sandbox_mismatch_requires_purge(self):
        instance = new_devbox(container_cli="docker")
        instance.nested_sandbox = True

        with mock.patch.object(
            instance,
            "container_inspect",
            return_value={"Config": {"Labels": {}}},
        ), mock.patch("sys.stderr", new_callable=io.StringIO) as stderr:
            with self.assertRaisesRegex(SystemExit, "1"):
                instance.ensure_nested_sandbox()

        self.assertIn("purge", stderr.getvalue())

    def test_ssh_port_mismatch_requires_purge(self):
        instance = new_devbox(container_cli="docker")
        instance.ssh_port = "2222"

        with mock.patch.object(
            instance,
            "container_inspect",
            return_value={"Config": {"Labels": {DEVBOX["SSH_PORT_LABEL"]: "2200"}}},
        ), mock.patch("sys.stderr", new_callable=io.StringIO) as stderr:
            with self.assertRaisesRegex(SystemExit, "1"):
                instance.ensure_ssh_port()

        self.assertIn("purge", stderr.getvalue())

    def test_nested_sandbox_adds_runtime_arguments(self):
        instance = new_devbox(container_cli="docker")
        instance.nested_sandbox = True

        with mock.patch.object(instance, "run_cli") as run_cli:
            instance.run_new_container()

        command = run_cli.call_args.args[0]
        self.assertIn("org.alexn.devbox.nested-sandbox=true", command)
        for capability in ("SYS_ADMIN", "SYS_CHROOT", "SETUID", "SETGID", "SYS_PTRACE"):
            self.assertIn(capability, command)
        self.assertIn("seccomp=unconfined", command)
        self.assertIn("apparmor=unconfined", command)

    def test_workspace_mount_accepts_docker_desktop_macos_source(self):
        instance = new_devbox(container_cli="docker", workspace_dir="/Users/alex/Developer")
        instance.workspace_mount_dir = "/Users/alex/Developer"
        instance.workspace_container_mount_dir = "/Users/alex/Developer"
        instance.workspace_container_dir = "/Users/alex/Developer"
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
            instance.ensure_workspace_configuration()

    def test_workspace_mount_mismatch_reports_running_and_current_configuration(self):
        instance = new_devbox(container_cli="docker", workspace_dir="/current/workspace")
        instance.workspace_mount_dir = "/current/workspace"
        instance.workspace_container_mount_dir = "/current/workspace"
        instance.workspace_container_dir = "/current/workspace/project"
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
                instance.ensure_workspace_configuration()

        output = stderr.getvalue()
        for expected in (
            "Running container configuration:",
            "Workspace: /running/workspace -> /running/workspace",
            "Workdir: /running/workspace/project",
            "Current configuration:",
            "Workspace: /current/workspace -> /current/workspace",
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

    def test_exec_converts_requested_host_directory_to_container_directory(self):
        instance = new_devbox("exec", command_args=["bash"], execution_dir=".")

        with mock.patch.object(instance, "assert_container_running"), mock.patch.object(
            instance, "container_directory", return_value="/workspace/project"
        ) as container_directory, mock.patch.object(instance, "exec_container") as exec_container:
            instance.exec_command()

        container_directory.assert_called_once_with(".")
        self.assertEqual(instance.execution_dir, "/workspace/project")
        exec_container.assert_called_once_with(["bash"])

    def test_purge_all_collects_managed_home_volume_not_custom_named_volume(self):
        instance = new_devbox("purge-all", container_cli="docker")
        container = {
            "Mounts": [
                {"Name": "devbox-home", "Destination": "/home/dev"},
                {"Name": "projects", "Destination": "/home/dev/Projects"},
            ]
        }
        volume_names = []

        with mock.patch.object(instance, "inspect_object", return_value=container):
            instance.collect_container_home_volumes(volume_names, "container-id")

        self.assertEqual(volume_names, ["devbox-home"])


class StatusTest(unittest.TestCase):
    def test_start_summary_reports_remote_ide_connection(self):
        instance = new_devbox("start", container_cli="docker")
        instance.mode = "container-native"
        instance.ssh_port = "2222"

        with mock.patch("sys.stdout", new_callable=io.StringIO) as stdout:
            instance.print_start_summary()

        self.assertIn("SSH:       dev@localhost:2222", stdout.getvalue())

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
                "Labels": {DEVBOX["SSH_PORT_LABEL"]: "2222"},
            },
            "State": {"Running": True, "Status": "running", "StartedAt": "2026-07-12T10:00:01Z"},
            "Mounts": [
                {"Source": "/host/project", "Destination": "/workspace/project", "RW": True},
                {"Name": "devbox-home", "Destination": "/home/dev", "RW": True},
                {"Source": "/host/wg.conf", "Destination": "/etc/wireguard/devbox.conf", "RW": False},
            ],
            "HostConfig": {
                "PortBindings": {
                    "22/tcp": [{"HostIp": "127.0.0.1", "HostPort": "2222"}],
                    "10012/tcp": [{"HostPort": "10012"}],
                }
            },
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
            "SSH:       dev@localhost:2222",
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

    def test_status_reports_container_native_mode_and_custom_volume_mapping(self):
        instance = new_devbox("status", container_cli="docker")
        container = {
            "Config": {
                "Labels": {DEVBOX["MODE_LABEL"]: "container-native"},
                "WorkingDir": "/home/dev",
            },
            "State": {"Running": True, "Status": "running"},
            "Mounts": [
                {"Name": "devbox-home", "Destination": "/home/dev", "RW": True},
                {"Name": "projects", "Destination": "/home/dev/projects", "RW": True},
            ],
        }

        with mock.patch.object(instance, "container_inspect", return_value=container), mock.patch(
            "sys.stdout", new_callable=io.StringIO
        ) as stdout:
            instance.status_container()

        output = stdout.getvalue()
        self.assertIn("Mode:      container-native", output)
        self.assertIn("Workdir:   /home/dev", output)
        self.assertIn("projects -> /home/dev/projects (rw)", output)


class ParserTest(unittest.TestCase):
    def test_status_parses_without_arguments(self):
        namespace = DEVBOX["build_parser"]().parse_args(["status"])

        self.assertEqual(namespace.command, "status")

    def test_start_and_compose_parse_optional_workspace(self):
        parser = DEVBOX["build_parser"]()

        for command in ("start", "compose"):
            with self.subTest(command=command):
                namespace = parser.parse_args([command, "--workspace", "/tmp/workspace"])
                self.assertEqual(namespace.command, command)
                self.assertEqual(namespace.workspace, "/tmp/workspace")

    def test_start_and_compose_without_workspace_create_native_instances_and_reject_positional_workspace(self):
        parser = DEVBOX["build_parser"]()

        for command in ("start", "compose"):
            with self.subTest(command=command):
                namespace = parser.parse_args([command])
                instance = DEVBOX["create_devbox"](namespace, "docker")
                self.assertEqual(instance.mode, "container-native")
                self.assertEqual(instance.workspace_dir, "")
                with mock.patch("sys.stderr", new_callable=io.StringIO), self.assertRaises(SystemExit):
                    parser.parse_args([command, "workspace"])

    def test_start_and_compose_parse_repeated_mount_options(self):
        parser = DEVBOX["build_parser"]()

        for command in ("start", "compose"):
            with self.subTest(command=command):
                namespace = parser.parse_args(
                    [command, "--mount", "/one:/home/dev/one", "--mount", "/two:/home/dev/two:ro"]
                )
                self.assertEqual(namespace.mounts, ["/one:/home/dev/one", "/two:/home/dev/two:ro"])

    def test_start_and_compose_parse_nested_sandbox_option(self):
        parser = DEVBOX["build_parser"]()

        for command in ("start", "compose"):
            with self.subTest(command=command):
                namespace = parser.parse_args([command, "--nested-sandbox"])
                self.assertTrue(namespace.nested_sandbox)

    def test_start_and_compose_parse_optional_ssh_port(self):
        parser = DEVBOX["build_parser"]()

        for command in ("start", "compose"):
            with self.subTest(command=command):
                namespace = parser.parse_args([command, "--ssh-port", "2222"])
                instance = DEVBOX["create_devbox"](namespace, "docker")

                self.assertEqual(instance.ssh_port, "2222")

    def test_ssh_port_rejects_values_outside_the_tcp_port_range(self):
        parser = DEVBOX["build_parser"]()

        for value in ("0", "65536", "not-a-port"):
            with self.subTest(value=value), mock.patch("sys.stderr", new_callable=io.StringIO):
                with self.assertRaisesRegex(SystemExit, "2"):
                    parser.parse_args(["start", "--ssh-port", value])

    def test_start_and_compose_parse_repeated_named_volumes(self):
        parser = DEVBOX["build_parser"]()

        for command in ("start", "compose"):
            with self.subTest(command=command):
                namespace = parser.parse_args(
                    [command, "--volume", "projects:~/projects:ro", "--volume", "cache:/cache"]
                )
                self.assertEqual(namespace.volumes, ["projects:~/projects:ro", "cache:/cache"])

    def test_exec_preserves_passthrough_arguments(self):
        namespace = DEVBOX["build_parser"]().parse_args(["exec", "python", "-c", "print('ok')"])

        self.assertEqual(namespace.command_args, ["python", "-c", "print('ok')"])

    def test_exec_parses_workdir_and_optional_delimiter(self):
        namespace = DEVBOX["build_parser"]().parse_args(
            ["exec", "--workdir", "~/projects", "--", "python", "-c", "print('ok')"]
        )

        self.assertEqual(namespace.execution_dir, "~/projects")
        self.assertEqual(namespace.command_args, ["--", "python", "-c", "print('ok')"])

    def test_exec_defaults_workdir_and_create_strips_optional_delimiter(self):
        namespace = DEVBOX["build_parser"]().parse_args(["exec", "--", "python", "-c", "print('ok')"])
        instance = DEVBOX["create_devbox"](namespace, "docker")

        self.assertEqual(namespace.execution_dir, ".")
        self.assertEqual(instance.execution_dir, ".")
        self.assertEqual(instance.command_args, ["python", "-c", "print('ok')"])

    def test_exec_treats_path_like_command_as_command(self):
        namespace = DEVBOX["build_parser"]().parse_args(["exec", "./script", "--flag"])
        instance = DEVBOX["create_devbox"](namespace, "docker")

        self.assertEqual(instance.execution_dir, ".")
        self.assertEqual(instance.command_args, ["./script", "--flag"])


if __name__ == "__main__":
    unittest.main()
