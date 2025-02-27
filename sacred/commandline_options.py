"""
Provides the basis for all command-line options (flags) in sacred.

It defines the base class CommandLineOption and the standard supported flags.
Some further options that add observers to the run are defined alongside those.
"""

import warnings
from typing import Callable
import inspect
import re

from sacred.run import Run
from sacred.commands import print_config
from sacred.settings import SETTINGS
from sacred.utils import convert_camel_case_to_snake_case, get_inheritors


CLIFunction = Callable[[str, Run], None]


class CLIOption:
    def __init__(
        self,
        apply_function: CLIFunction,
        short_flag: str,
        long_flag: str,
        is_flag: bool,
    ):

        if not re.match(r"-\w$", short_flag):
            raise ValueError(
                "Short flag malformed. " "One correct short flag would be: `-j`."
            )
        if not re.match(r"--[\w-]+\w$", long_flag):
            raise ValueError(
                "Long flag malformed. One correct long flag "
                "would be: `--my-pretty-flag`"
            )
        self.apply_function = apply_function
        self.short_flag = short_flag
        self.long_flag = long_flag
        self.is_flag = is_flag

        # trick for backward compatibility:
        self.arg = None if is_flag else "VALUE"
        self.arg_description = None if is_flag else ""

    def __call__(self, *args, **kwargs):
        return self.apply_function(*args, **kwargs)

    def get_flag(self):
        """Legacy function. Should be removed at some point."""
        return self.long_flag

    def get_short_flag(self):
        """Legacy function. Should be removed at some point."""
        return self.short_flag

    def get_flags(self):
        """Legacy function. Should be removed at some point."""
        return self.short_flag, self.long_flag

    def apply(self, args, run):
        """Legacy function. Should be removed at some point."""
        return self.apply_function(args, run)

    def get_name(self):
        return self.apply_function.__name__

    def get_description(self):
        return inspect.getdoc(self.apply_function) or ""


def cli_option(short_flag: str, long_flag: str, is_flag=False):
    def wrapper(f: CLIFunction):
        return CLIOption(f, short_flag, long_flag, is_flag)

    return wrapper


class CommandLineOption:
    """
    Base class for all command-line options.

    To implement a new command-line option just inherit from this class.
    Then add the `flag` class-attribute to specify the name and a class
    docstring with the description.
    If your command-line option should take an argument you must also provide
    its name via the `arg` class attribute and its description as
    `arg_description`.
    Finally you need to implement the `execute` classmethod. It receives the
    value of the argument (if applicable) and the current run. You can modify
    the run object in any way.

    If the command line option depends on one or more installed packages, those
    should be imported in the `apply` method to get a proper ImportError
    if the packages are not available.
    """

    _enabled = True

    short_flag = None
    """ The (one-letter) short form (defaults to first letter of flag) """

    arg = None
    """ Name of the argument (optional) """

    arg_description = None
    """ Description of the argument (optional) """

    @classmethod
    def get_flag(cls):
        # Get the flag name from the class name
        flag = cls.__name__
        if flag.endswith("Option"):
            flag = flag[:-6]
        return "--" + convert_camel_case_to_snake_case(flag)

    @classmethod
    def get_short_flag(cls):
        if cls.short_flag is None:
            return "-" + cls.get_flag()[2]
        else:
            return "-" + cls.short_flag

    @classmethod
    def get_flags(cls):
        """
        Return the short and the long version of this option.

        The long flag (e.g. '--foo_bar'; used on the command-line like this:
        --foo_bar[=ARGS]) is derived from the class-name by stripping away any
        -Option suffix and converting the rest to snake_case.

        The short flag (e.g. '-f'; used on the command-line like this:
        -f [ARGS]) the short_flag class-member if that is set, or the first
        letter of the long flag otherwise.

        Returns
        -------
        (str, str)
            tuple of short-flag, and long-flag

        """
        return cls.get_short_flag(), cls.get_flag()

    @classmethod
    def apply(cls, args, run):
        """
        Modify the current Run base on this command-line option.

        This function is executed after constructing the Run object, but
        before actually starting it.

        Parameters
        ----------
        args : bool | str
            If this command-line option accepts an argument this will be value
            of that argument if set or None.
            Otherwise it is either True or False.
        run :  sacred.run.Run
            The current run to be modified

        """
        pass


def get_name(option):
    if isinstance(option, CLIOption):
        return option.get_name()
    else:
        return option.__name__


def gather_command_line_options(filter_disabled=None):
    """Get a sorted list of all CommandLineOption subclasses."""
    if filter_disabled is None:
        filter_disabled = not SETTINGS.COMMAND_LINE.SHOW_DISABLED_OPTIONS

    options = []
    for opt in get_inheritors(CommandLineOption):
        warnings.warn(
            "Subclassing `CommandLineOption` is deprecated. Please "
            "use the `sacred.cli_option` decorator and pass the function "
            "to the Experiment constructor."
        )
        if filter_disabled and not opt._enabled:
            continue
        options.append(opt)

    options += DEFAULT_COMMAND_LINE_OPTIONS

    return sorted(options, key=get_name)


class HelpOption(CommandLineOption):
    """Print this help message and exit."""


@cli_option("-d", "--debug", is_flag=True)
def debug_option(args, run):
    """
    Set this run to debug mode.

    Suppress warnings about missing observers and don't filter the stacktrace.
    Also enables usage with ipython --pdb.
    """
    run.debug = True


class PDBOption(CommandLineOption):
    """Automatically enter post-mortem debugging with pdb on failure."""

    short_flag = "D"

    @classmethod
    def apply(cls, args, run):
        run.pdb = True


@cli_option("-l", "--loglevel")
def loglevel_option(args, run):
    """
    Set the LogLevel.

    Loglevel either as 0 - 50 or as string: DEBUG(10),
    INFO(20), WARNING(30), ERROR(40), CRITICAL(50)
    """
    # TODO: sacred.initialize.create_run already takes care of this

    try:
        lvl = int(args)
    except ValueError:
        lvl = args
    run.root_logger.setLevel(lvl)


class CommentOption(CommandLineOption):
    """Adds a message to the run."""

    arg = "COMMENT"
    arg_description = "A comment that should be stored along with the run."

    @classmethod
    def apply(cls, args, run):
        """Add a comment to this run."""
        run.meta_info["comment"] = args


class BeatIntervalOption(CommandLineOption):
    """Control the rate of heartbeat events."""

    arg = "BEAT_INTERVAL"
    arg_description = "Time between two heartbeat events measured in seconds."

    @classmethod
    def apply(cls, args, run):
        """Set the heart-beat interval for this run."""
        run.beat_interval = float(args)


class UnobservedOption(CommandLineOption):
    """Ignore all observers for this run."""

    @classmethod
    def apply(cls, args, run):
        """Set this run to unobserved mode."""
        run.unobserved = True


class QueueOption(CommandLineOption):
    """Only queue this run, do not start it."""

    @classmethod
    def apply(cls, args, run):
        """Set this run to queue only mode."""
        run.queue_only = True


class ForceOption(CommandLineOption):
    """Disable warnings about suspicious changes for this run."""

    @classmethod
    def apply(cls, args, run):
        """Set this run to not warn about suspicous changes."""
        run.force = True


class PriorityOption(CommandLineOption):
    """Sets the priority for a queued up experiment."""

    short_flag = "P"
    arg = "PRIORITY"
    arg_description = "The (numeric) priority for this run."

    @classmethod
    def apply(cls, args, run):
        """Add priority info for this run."""
        try:
            priority = float(args)
        except ValueError:
            raise ValueError(
                "The PRIORITY argument must be a number! " "(but was '{}')".format(args)
            )
        run.meta_info["priority"] = priority


class EnforceCleanOption(CommandLineOption):
    """Fail if any version control repository is dirty."""

    @classmethod
    def apply(cls, args, run):
        try:
            import git  # NOQA
        except ImportError:
            warnings.warn(
                "GitPython must be installed to use the " "--enforce-clean option."
            )
            raise
        repos = run.experiment_info["repositories"]
        if not repos:
            raise RuntimeError(
                "No version control detected. "
                "Cannot enforce clean repository.\n"
                "Make sure that your sources under VCS and the "
                "corresponding python package is installed."
            )
        else:
            for repo in repos:
                if repo["dirty"]:
                    raise RuntimeError(
                        "EnforceClean: Uncommited changes in "
                        'the "{}" repository.'.format(repo)
                    )


class PrintConfigOption(CommandLineOption):
    """Always print the configuration first."""

    @classmethod
    def apply(cls, args, run):
        print_config(run)
        print("-" * 79)


class NameOption(CommandLineOption):
    """Set the name for this run."""

    arg = "NAME"
    arg_description = "Name for this run."

    @classmethod
    def apply(cls, args, run):
        run.experiment_info["name"] = args
        run.run_logger = run.root_logger.getChild(args)


class CaptureOption(CommandLineOption):
    """Control the way stdout and stderr are captured."""

    short_flag = "C"
    arg = "CAPTURE_MODE"
    arg_description = "stdout/stderr capture mode. One of [no, sys, fd]"

    @classmethod
    def apply(cls, args, run):
        run.capture_mode = args


DEFAULT_COMMAND_LINE_OPTIONS = [debug_option, loglevel_option]
