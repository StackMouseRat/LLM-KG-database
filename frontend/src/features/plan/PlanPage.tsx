import type { UsePlanPipelineResult } from './usePlanPipeline';
import { PlanInputCard } from './PlanInputCard';
import { PlanChapterGrid } from './PlanChapterGrid';
import { CaseSearchPanel } from './CaseSearchPanel';

type PlanPageProps = {
  plan: UsePlanPipelineResult;
  showModeTags: boolean;
  showCompactLayout: boolean;
};

export function PlanPage({ plan, showModeTags, showCompactLayout }: PlanPageProps) {
  return (
    <div className="pipeline-page">
      <PlanInputCard plan={plan} />
      <PlanChapterGrid chapters={plan.chapters} showModeTags={showModeTags} showCompactLayout={showCompactLayout} />
      <CaseSearchPanel plan={plan} showModeTags={showModeTags} />
    </div>
  );
}
