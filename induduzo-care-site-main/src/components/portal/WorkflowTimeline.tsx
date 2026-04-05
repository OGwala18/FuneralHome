import { Check, Circle, Clock } from 'lucide-react';
import { cn } from '@/lib/utils';
import type { WorkflowStage } from '@/types';

interface WorkflowTimelineProps {
  stages: WorkflowStage[];
}

export default function WorkflowTimeline({ stages }: WorkflowTimelineProps) {
  return (
    <div className="relative">
      {stages.map((stage, index) => {
        const isLast = index === stages.length - 1;
        return (
          <div key={stage.key} className="flex gap-4">
            {/* Vertical line + node */}
            <div className="flex flex-col items-center">
              <div
                className={cn(
                  'flex items-center justify-center w-8 h-8 rounded-full border-2 flex-shrink-0',
                  stage.status === 'completed' && 'bg-green-100 border-green-500 text-green-600',
                  stage.status === 'current' && 'bg-primary/10 border-primary text-primary animate-pulse',
                  stage.status === 'upcoming' && 'bg-gray-50 border-gray-300 text-gray-400'
                )}
              >
                {stage.status === 'completed' && <Check className="h-4 w-4" />}
                {stage.status === 'current' && <Clock className="h-4 w-4" />}
                {stage.status === 'upcoming' && <Circle className="h-3 w-3" />}
              </div>
              {!isLast && (
                <div
                  className={cn(
                    'w-0.5 flex-1 min-h-[32px]',
                    stage.status === 'completed' ? 'bg-green-300' : 'bg-gray-200 border-dashed'
                  )}
                />
              )}
            </div>

            {/* Content */}
            <div className={cn('pb-6', isLast && 'pb-0')}>
              <p
                className={cn(
                  'text-sm font-medium leading-8',
                  stage.status === 'completed' && 'text-green-700',
                  stage.status === 'current' && 'text-foreground',
                  stage.status === 'upcoming' && 'text-muted-foreground'
                )}
              >
                {stage.label}
              </p>
              {stage.note && (
                <p className="text-xs text-muted-foreground mt-0.5">{stage.note}</p>
              )}
              {stage.completedAt && (
                <p className="text-xs text-muted-foreground mt-0.5">
                  Completed {new Date(stage.completedAt).toLocaleDateString('en-ZA')}
                </p>
              )}
            </div>
          </div>
        );
      })}
    </div>
  );
}
