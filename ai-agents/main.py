"""
Main entry point for the Children's Video Content Evaluation System.
Complete workflow: YouTube URL → Video Download → Data Extraction → Evaluation
"""

import os
import sys
import argparse
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Add paths
PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT / "evaluation"))
sys.path.insert(0, str(PROJECT_ROOT / "video_data_extraction"))

from evaluation.evaluate_video import evaluate_video, save_results, print_summary


def extract_video_data(youtube_url: str, output_dir: Path) -> dict:
    """
    Extract video data from YouTube URL.
    
    Args:
        youtube_url: YouTube video URL
        output_dir: Directory to save outputs
        
    Returns:
        Dictionary with extraction results
    """
    from video_data_extraction.main import process_youtube_video
    
    print("\n" + "="*70)
    print("STEP 1: VIDEO DATA EXTRACTION".center(70))
    print("="*70)
    print()
    
    result = process_youtube_video(
        youtube_url,
        output_dir=str(output_dir),
        use_chunked_processing=False,  # FAST MODE: skip visual/LLM analysis
        segment_duration=30.0,
        frames_per_segment=20,
        audio_chunk_duration=60.0,
    )
    
    print("\n✅ Video data extraction complete!")
    print(f"⏱️  Processing time: {result['duration']:.1f} seconds")
    print()
    
    return result


def evaluate_extracted_video(output_dir: Path, child_age: float, api_key: str) -> dict:
    """
    Evaluate the extracted video data.
    
    Args:
        output_dir: Directory containing extracted data
        child_age: Age of child in years

        api_key: Anthropic API key

    Returns:
        Evaluation results dictionary
    """
    video_path = output_dir / "video_with_audio.mp4"
    
    print("\n" + "="*70)
    print("STEP 2: CONTENT EVALUATION".center(70))
    print("="*70)
    print()
    
    if not video_path.exists():
        raise FileNotFoundError(f"Video not found: {video_path}")
    
    # Run evaluation (FAST MODE - no LLM client needed)
    print("🚀 Starting evaluation...")
    print(f"👶 Child age: {child_age} years")
    print()
    
    results = evaluate_video(
        video_path=str(video_path),
        child_age=child_age,
        llm_client=None,
        outputs_dir=str(output_dir),
        compute_motion=False  # Skip heavy motion analysis for speed
    )
    
    # Save results
    results_path = output_dir / "evaluation_results.json"
    save_results(results, str(results_path))
    
    # Print summary
    print_summary(results)
    
    # Quick insights
    print("\n" + "="*70)
    print("💡 FINAL ASSESSMENT".center(70))
    print("="*70)
    
    dev_score = results["overall_scores"]["development_score"]
    brainrot = results["overall_scores"]["brainrot_index"]
    
    if dev_score >= 75 and brainrot <= 30:
        print("\n✅ This content appears to be HIGH QUALITY and age-appropriate!")
        print("   Safe for regular viewing.")
    elif dev_score >= 60 and brainrot <= 50:
        print("\n⚠️  This content is generally ACCEPTABLE but has some concerns.")
        print("   Consider viewing with supervision.")
    else:
        print("\n❌ This content has SIGNIFICANT developmental concerns.")
        print("   Consider alternative content for this age group.")
    
    # Highlight concerns and strengths
    concerns = results["recommendations"]["concerns"]
    if concerns:
        print("\n📋 Key Areas to Watch:")
        for concern in concerns[:3]:
            print(f"   • {concern}")
    
    strengths = results["recommendations"]["strengths"]
    if strengths:
        print("\n✨ Positive Aspects:")
        for strength in strengths[:3]:
            print(f"   • {strength}")
    
    print("\n" + "="*70)
    print(f"📊 Full results saved to: {results_path}")
    print("="*70)
    print()
    
    return results


def main():
    """
    Main orchestration function.
    Handles command-line arguments and runs the complete pipeline.
    """
    parser = argparse.ArgumentParser(
        description="Children's Video Content Evaluator - Complete Pipeline",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Evaluate a YouTube video for a 4-year-old
  python main.py --url "https://youtube.com/watch?v=..." --age 4

  # Evaluate for a different age
  python main.py --url "https://youtube.com/watch?v=..." --age 6

  # Specify custom output directory
  python main.py --url "https://youtube.com/watch?v=..." --age 4 --output my_outputs
        """
    )
    
    parser.add_argument(
        "--url",
        type=str,
        required=True,
        help="YouTube video URL to evaluate"
    )
    
    parser.add_argument(
        "--age",
        type=float,
        required=True,
        help="Child's age in years (e.g., 4, 5.5)"
    )
    
    parser.add_argument(
        "--output",
        type=str,
        default="outputs",
        help="Output directory for all files (default: outputs)"
    )
    
    parser.add_argument(
        "--skip-extraction",
        action="store_true",
        help="Skip video extraction (use existing data in output directory)"
    )
    
    args = parser.parse_args()
    
    # Validate inputs
    if not (0 <= args.age <= 10):
        print(f"⚠️  Warning: Age {args.age} is outside typical range (0-8 years)")
        response = input("Continue anyway? (y/n): ")
        if response.lower() != 'y':
            sys.exit(0)
    
    # API key is optional in fast mode (LLM disabled by default)
    api_key = os.getenv("ANTHROPIC_API_KEY")
    
    # Setup output directory
    output_dir = PROJECT_ROOT / args.output
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Print header
    print("\n" + "="*70)
    print("CHILDREN'S VIDEO CONTENT EVALUATOR".center(70))
    print("Complete Pipeline: Download → Extract → Evaluate".center(70))
    print("="*70)
    print()
    print(f"📺 YouTube URL: {args.url}")
    print(f"👶 Child Age: {args.age} years")
    print(f"📁 Output Directory: {output_dir}")
    print()
    
    try:
        # Step 1: Extract video data (unless skipped)
        if not args.skip_extraction:
            extraction_result = extract_video_data(args.url, output_dir)
        else:
            print("\n⏭️  Skipping video extraction (using existing data)")
            print()
        
        # Step 2: Evaluate the video
        evaluation_result = evaluate_extracted_video(output_dir, args.age, api_key)
        
        # Final success message
        print("\n" + "="*70)
        print("🎉 PIPELINE COMPLETE!".center(70))
        print("="*70)
        print()
        print(f"✅ Video downloaded and extracted")
        print(f"✅ Content analyzed and evaluated")
        print(f"✅ All files saved to: {output_dir.absolute()}")
        print()
        print("📂 Generated files:")
        print("   • video_with_audio.mp4 - Full video")
        print("   • audio_only.m4a - Audio track")
        print("   • speech_transcript.txt - Speech transcription")
        print("   • video_llm_transcript.txt - Visual analysis")
        print("   • dialogue_transcript.txt - Dialogue breakdown")
        print("   • scene_summary.txt - Scene analysis")
        print("   • evaluation_results.json - ⭐ Final scores!")
        print()
        print("="*70)
        print()
        
    except KeyboardInterrupt:
        print("\n\n⚠️  Process interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()

