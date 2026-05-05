"""CLI application entry point."""

import click
import logging
import sys
from pathlib import Path
from rich.console import Console
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, TextColumn

from magnific.config.loader import ConfigLoader
from magnific.config.models import PipelineConfig
from magnific.orchestrator import Orchestrator
from magnific.core.errors import MagnificError, InvalidApiKeyError

console = Console()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stderr)],
)


@click.group()
@click.version_option(version="1.0.0")
def main():
    """Magnific - Creative video pipeline from character references."""
    pass


@main.command("generate-config")
@click.option("--idea", "-i", required=True, help="Creative brief describing the story")
@click.option("--ref1", "-1", required=True, type=Path, help="First character reference image")
@click.option("--ref2", "-2", required=True, type=Path, help="Second character reference image")
@click.option("--output", "-o", default="workflow.yaml", type=Path, help="Output config file path")
@click.option("--scene-count", type=int, default=5, help="Number of scenes to generate")
@click.option("--duration", type=int, default=5, help="Video duration per scene (seconds)")
@click.option("--interactive", is_flag=True, help="Enable LLM-driven interactive refinement")
def generate_config(
    idea: str,
    ref1: Path,
    ref2: Path,
    output: Path,
    scene_count: int,
    duration: int,
    interactive: bool,
):
    """Generate a workflow configuration file from a creative idea.
    
    With --interactive flag: LLM helps refine your idea and suggests scenes.
    Without flag: Static template generation (original behavior).
    """
    try:
        # Validate inputs
        if not ref1.exists():
            console.print(f"[red]Error: Reference image 1 not found: {ref1}[/red]")
            raise SystemExit(1)
        if not ref2.exists():
            console.print(f"[red]Error: Reference image 2 not found: {ref2}[/red]")
            raise SystemExit(1)
        
        if interactive:
            # NEW: Interactive LLM-driven generation
            console.print("[blue]Starting interactive LLM session...[/blue]")
            console.print(f"  Idea: {idea[:50]}...")
            console.print(f"  References: {ref1.name}, {ref2.name}")
            console.print()
            
            # Import workflow generator
            from magnific.workflow.interactive_generator import InteractiveWorkflowGenerator
            
            generator = InteractiveWorkflowGenerator()
            
            # Start interactive session
            import asyncio
            session = asyncio.run(
                generator.start_session(
                    idea=idea,
                    reference_images=[ref1, ref2]
                )
            )
            
            # Display character analysis
            if session.character_analysis:
                console.print("[green]Character Analysis:[/green]")
                console.print(f"  {session.character_analysis[:200]}...")
                console.print()
            
            # Display suggested scenes
            if session.suggested_scenes:
                console.print("[yellow]Suggested Scenes:[/yellow]")
                for scene in session.suggested_scenes:
                    title = scene.get("title", "Untitled")
                    console.print(f"  {scene.get('scene_number', '?')}. {title}")
                console.print()
            
            # Display tone/setting suggestions
            if session.tone:
                console.print(f"[cyan]Suggested Tone: {session.tone}[/cyan]")
            if session.setting:
                console.print(f"[cyan]Suggested Setting: {session.setting}[/cyan]")
            console.print()
            
            # Interactive refinement loop
            console.print("[bold]Interactive Refinement[/bold]")
            console.print("Type 'generate' to create config, or provide refinements:")
            console.print()
            
            while True:
                user_input = console.input("[cyan]Your input: [/cyan]")
                
                if user_input.lower().strip() == "generate":
                    # Generate final config
                    console.print("[blue]Generating final config...[/blue]")
                    config = asyncio.run(
                        generator.generate_config(session, output)
                    )
                    console.print(f"[green]✓ Config written to: {output}[/green]")
                    console.print()
                    console.print("[yellow]Next steps:[/yellow]")
                    console.print("  1. Set GOOGLE_API_KEY environment variable")
                    console.print("  2. Set GOOGLE_CLOUD_PROJECT environment variable")
                    console.print("  3. Run: magnific run --config {output}")
                    break
                
                # Refine with user input
                console.print("[blue]Refining suggestions...[/blue]")
                session = asyncio.run(
                    generator.refine(session, user_input)
                )
                
                # Display updated scenes
                if session.suggested_scenes:
                    console.print("[green]Updated Scenes:[/green]")
                    for scene in session.suggested_scenes:
                        title = scene.get("title", "Untitled")
                        console.print(f"  {scene.get('scene_number', '?')}. {title}")
                    console.print()
        
        else:
            # Original: Static template generation
            console.print(f"[blue]Generating workflow config...[/blue]")
            console.print(f"  Idea: {idea[:50]}...")
            console.print(f"  References: {ref1.name}, {ref2.name}")
            
            # Generate config
            config = ConfigLoader.generate_workflow_config(
                idea=idea,
                reference_images=[ref1, ref2],
                output_path=output,
            )
            
            console.print(f"[green]✓ Config written to: {output}[/green]")
            console.print(f"\n[yellow]Next steps:[/yellow]")
            console.print(f"  1. Set GOOGLE_API_KEY environment variable")
            console.print(f"  2. Run: magnific run --config {output}")
        
    except MagnificError as e:
        console.print(f"[red]Error: {e}[/red]")
        raise SystemExit(1)


@main.command("run")
@click.option("--config", "-c", required=True, type=Path, help="Workflow config file")
@click.option("--from-stage", type=click.Choice(["story", "preview", "video"]), help="Resume from stage")
@click.option("--only-stage", type=click.Choice(["story", "preview", "video"]), help="Run only this stage")
@click.option("--job-id", type=str, help="Existing job ID to resume")
@click.option("--set", "-s", multiple=True, help="Override config value (key=value)")
@click.option("--verbose", "-v", is_flag=True, help="Verbose output")
def run_pipeline(
    config: Path,
    from_stage: str | None,
    only_stage: str | None,
    job_id: str | None,
    set: tuple[str, ...],
    verbose: bool,
):
    """Run the Magnific pipeline."""
    try:
        # Load config
        console.print(f"[blue]Loading config from: {config}[/blue]")
        
        overrides = {}
        for s in set:
            if "=" in s:
                key, value = s.split("=", 1)
                overrides[key] = value
        
        pipeline_config = ConfigLoader.load(config, overrides)
        
        # Validate API key
        try:
            ConfigLoader.validate_api_key()
        except InvalidApiKeyError as e:
            console.print(f"[red]Error: {e}[/red]")
            console.print("[yellow]Set your API key: export GOOGLE_API_KEY='your-key'[/yellow]")
            raise SystemExit(1)
        
        # Create orchestrator
        orchestrator = Orchestrator(pipeline_config)
        
        console.print(f"\n[blue]Starting pipeline...[/blue]")
        
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            task = progress.add_task("Running pipeline...", total=None)
            
            # Run pipeline (async)
            import asyncio
            status = asyncio.run(
                orchestrator.run(
                    job_id=job_id,
                    from_stage=from_stage,
                    only_stage=only_stage,
                )
            )
        
        # Print summary
        summary = orchestrator.get_job_summary()
        
        console.print(f"\n[green]✓ Pipeline complete[/green]")
        console.print(f"  Job ID: {summary.get('job_id')}")
        console.print(f"  Status: {summary.get('status')}")
        
        table = Table(title="Stage Results")
        table.add_column("Stage")
        table.add_column("Success")
        table.add_column("Failed")
        
        for stage in ["story", "preview", "video"]:
            success = summary.get(f"{stage}_success", 0)
            failed = summary.get(f"{stage}_failed", 0)
            table.add_row(stage, str(success), str(failed))
        
        console.print(table)
        
        console.print(f"\n[yellow]Output directory: {summary.get('workspace')}[/yellow]")
        
    except MagnificError as e:
        console.print(f"[red]Error: {e}[/red]")
        raise SystemExit(1)
    except Exception as e:
        console.print(f"[red]Unexpected error: {e}[/red]")
        if verbose:
            console.print_exception()
        raise SystemExit(1)


@main.command("status")
@click.option("--job-id", required=True, type=str, help="Job ID to inspect")
@click.option("--output-dir", type=Path, default=Path("./jobs"), help="Jobs directory")
def check_status(job_id: str, output_dir: Path):
    """Check job status."""
    try:
        job_dir = output_dir / job_id
        
        if not job_dir.exists():
            console.print(f"[red]Error: Job not found: {job_id}[/red]")
            raise SystemExit(1)
        
        # Load manifests
        from magnific.core.manifest import (
            JobStatusManifest,
            StoryManifest,
            PreviewManifest,
            VideoManifest,
        )
        
        console.print(f"\n[blue]Job: {job_id}[/blue]")
        
        # Job status
        status_path = job_dir / "job_status.json"
        if status_path.exists():
            status = JobStatusManifest.from_file(status_path)
            console.print(f"  Status: [green]{status.status.value}[/green]")
            console.print(f"  Created: {status.created_at}")
            console.print(f"  Updated: {status.updated_at}")
        
        # Stage details
        table = Table(title="Stage Progress")
        table.add_column("Stage")
        table.add_column("Status")
        table.add_column("Scenes")
        table.add_column("Success")
        table.add_column("Failed")
        
        manifests = {
            "story": (job_dir / "story_manifest.json", StoryManifest),
            "preview": (job_dir / "preview_manifest.json", PreviewManifest),
            "video": (job_dir / "video_manifest.json", VideoManifest),
        }
        
        for stage_name, (path, cls) in manifests.items():
            if path.exists():
                manifest = cls.from_file(path)
                table.add_row(
                    stage_name,
                    "✓",
                    str(len(manifest.scenes)),
                    str(manifest.completed_count),
                    str(manifest.failed_count),
                )
            else:
                table.add_row(stage_name, "pending", "-", "-", "-")
        
        console.print(table)
        
        # Failed scenes
        for stage_name, (path, cls) in manifests.items():
            if path.exists():
                manifest = cls.from_file(path)
                failed = [s for s in manifest.scenes if s.status.value in ("failed", "blocked")]
                if failed:
                    console.print(f"\n[red]Failed scenes in {stage_name}:[/red]")
                    for scene in failed:
                        console.print(f"  {scene.scene_id}: {scene.error}")
        
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise SystemExit(1)


if __name__ == "__main__":
    main()