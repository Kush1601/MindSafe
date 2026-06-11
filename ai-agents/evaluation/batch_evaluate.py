"""
Batch evaluation script for processing multiple videos from outputs folder.
"""

import os
import sys
import json
import argparse
from pathlib import Path
from typing import List, Dict, Any
from evaluation.evaluate_video import evaluate_video, save_results, print_summary
from evaluation.llm_client import LLMClient


def find_videos_in_outputs(outputs_dir: str) -> List[Dict[str, str]]:
    """
    Find video files in outputs directory structure.
    
    Args:
        outputs_dir: Path to outputs directory
        
    Returns:
        List of dicts with video_path and associated output paths
    """
    videos = []
    outputs_path = Path(outputs_dir)
    
    # Look for video files
    video_extensions = {'.mp4', '.avi', '.mov', '.mkv', '.webm', '.m4a'}
    
    for video_file in outputs_path.rglob('*'):
        if video_file.suffix.lower() in video_extensions:
            # Find associated files in same directory
            video_dir = video_file.parent
            
            video_info = {
                'video_path': str(video_file),
                'outputs_dir': str(video_dir),
                'video_name': video_file.stem
            }
            
            videos.append(video_info)
    
    return videos


def batch_evaluate(outputs_dir: str,
                   child_age: float,
                   output_dir: str = None,
                   api_key: str = None,
                   compute_motion: bool = False) -> List[Dict[str, Any]]:
    """
    Batch evaluate all videos in outputs directory.
    
    Args:
        outputs_dir: Directory containing video outputs
        child_age: Age of child in years
        output_dir: Directory to save results (default: outputs_dir/evaluations)
        api_key: Anthropic API key
        compute_motion: Whether to compute motion metrics
        
    Returns:
        List of evaluation results
    """
    # Find videos
    print(f"Scanning for videos in: {outputs_dir}")
    videos = find_videos_in_outputs(outputs_dir)
    
    if not videos:
        print("No videos found!")
        return []
    
    print(f"Found {len(videos)} video(s)\n")
    
    # Setup output directory
    if output_dir is None:
        output_dir = os.path.join(outputs_dir, "evaluations")
    
    os.makedirs(output_dir, exist_ok=True)
    
    # Initialize LLM client once
    llm_client = LLMClient(api_key=api_key)
    
    # Process each video
    all_results = []
    
    for i, video_info in enumerate(videos, 1):
        video_path = video_info['video_path']
        video_name = video_info['video_name']
        
        print(f"\n{'='*60}")
        print(f"Processing {i}/{len(videos)}: {video_name}")
        print(f"{'='*60}")
        
        try:
            # Evaluate
            results = evaluate_video(
                video_path=video_path,
                child_age=child_age,
                llm_client=llm_client,
                outputs_dir=video_info['outputs_dir'],
                compute_motion=compute_motion
            )
            
            # Save individual results
            result_path = os.path.join(output_dir, f"{video_name}_evaluation.json")
            save_results(results, result_path)
            
            # Print summary
            print_summary(results)
            
            all_results.append(results)
            
        except Exception as e:
            print(f"Error evaluating {video_name}: {e}")
            import traceback
            traceback.print_exc()
            continue
    
    # Save combined results
    combined_path = os.path.join(output_dir, "all_evaluations.json")
    with open(combined_path, 'w', encoding='utf-8') as f:
        json.dump(all_results, f, indent=2, ensure_ascii=False)
    
    print(f"\n{'='*60}")
    print(f"Batch evaluation complete!")
    print(f"Processed {len(all_results)}/{len(videos)} videos successfully")
    print(f"Results saved to: {output_dir}")
    print(f"{'='*60}\n")
    
    return all_results


def generate_comparison_report(results: List[Dict[str, Any]], output_path: str):
    """
    Generate a comparison report for multiple videos.
    
    Args:
        results: List of evaluation results
        output_path: Path to save comparison report
    """
    if not results:
        return
    
    report = {
        "summary": {
            "total_videos": len(results),
            "average_dev_score": sum(r["overall_scores"]["development_score"] for r in results) / len(results),
            "average_brainrot_index": sum(r["overall_scores"]["brainrot_index"] for r in results) / len(results)
        },
        "rankings": {
            "by_dev_score": sorted(
                [{"name": r["metadata"]["video_name"], 
                  "score": r["overall_scores"]["development_score"]} 
                 for r in results],
                key=lambda x: x["score"],
                reverse=True
            ),
            "by_brainrot_index": sorted(
                [{"name": r["metadata"]["video_name"], 
                  "score": r["overall_scores"]["brainrot_index"]} 
                 for r in results],
                key=lambda x: x["score"]
            )
        },
        "dimension_averages": {}
    }
    
    # Compute dimension averages
    if results:
        dimensions = results[0]["dimension_scores"].keys()
        for dim in dimensions:
            scores = [r["dimension_scores"][dim] for r in results]
            report["dimension_averages"][dim] = sum(scores) / len(scores)
    
    # Save report
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    
    print(f"Comparison report saved to: {output_path}")
    
    # Print summary
    print("\n" + "="*60)
    print("COMPARISON SUMMARY")
    print("="*60)
    print(f"\nTotal Videos: {report['summary']['total_videos']}")
    print(f"Average Dev Score: {report['summary']['average_dev_score']:.1f}/100")
    print(f"Average Brainrot Index: {report['summary']['average_brainrot_index']:.1f}/100")
    
    print("\nTop 3 by Development Score:")
    for i, item in enumerate(report['rankings']['by_dev_score'][:3], 1):
        print(f"  {i}. {item['name']}: {item['score']:.1f}")
    
    print("\nLowest 3 by Brainrot Index:")
    for i, item in enumerate(report['rankings']['by_brainrot_index'][:3], 1):
        print(f"  {i}. {item['name']}: {item['score']:.1f}")
    
    print("\n" + "="*60 + "\n")


def main():
    """Command-line interface for batch evaluation."""
    parser = argparse.ArgumentParser(
        description="Batch evaluate multiple videos from outputs folder"
    )
    parser.add_argument(
        "outputs_dir",
        help="Path to outputs directory containing videos"
    )
    parser.add_argument(
        "--age",
        type=float,
        required=True,
        help="Child's age in years"
    )
    parser.add_argument(
        "--output-dir",
        help="Directory to save evaluation results (default: outputs_dir/evaluations)"
    )
    parser.add_argument(
        "--no-motion",
        action="store_true",
        help="Skip motion computation (faster)"
    )
    parser.add_argument(
        "--api-key",
        help="Anthropic API key (or set ANTHROPIC_API_KEY env var)"
    )
    parser.add_argument(
        "--comparison-report",
        action="store_true",
        help="Generate comparison report across all videos"
    )
    
    args = parser.parse_args()
    
    # Validate inputs
    if not os.path.exists(args.outputs_dir):
        print(f"Error: Outputs directory not found: {args.outputs_dir}")
        sys.exit(1)
    
    # Get API key
    api_key = args.api_key or os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        print("Error: Anthropic API key required. Set ANTHROPIC_API_KEY env var or use --api-key")
        sys.exit(1)
    
    # Run batch evaluation
    try:
        results = batch_evaluate(
            outputs_dir=args.outputs_dir,
            child_age=args.age,
            output_dir=args.output_dir,
            api_key=api_key,
            compute_motion=not args.no_motion
        )
        
        # Generate comparison report if requested
        if args.comparison_report and results:
            output_dir = args.output_dir or os.path.join(args.outputs_dir, "evaluations")
            report_path = os.path.join(output_dir, "comparison_report.json")
            generate_comparison_report(results, report_path)
        
    except Exception as e:
        print(f"\nError during batch evaluation: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()

