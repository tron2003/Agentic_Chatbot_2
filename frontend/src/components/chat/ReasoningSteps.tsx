import React, { useState } from 'react';
import { ChevronDown, ChevronUp, Brain, Zap, CheckCircle2, AlertCircle } from 'lucide-react';
import { cn } from '@/lib/utils';
import type { ReasoningStep } from '@/lib/api';

interface ReasoningStepsProps {
  steps: ReasoningStep[];
  isComplete?: boolean;
}

export function ReasoningSteps({ steps, isComplete }: ReasoningStepsProps) {
  const [isExpanded, setIsExpanded] = useState(true);

  if (!steps || steps.length === 0) {
    return null;
  }

  const getIcon = (type: string) => {
    switch (type) {
      case 'thinking':
        return <Brain className="w-4 h-4 text-blue-500" />;
      case 'tool_call':
        return <Zap className="w-4 h-4 text-amber-500" />;
      case 'tool_result':
        return <CheckCircle2 className="w-4 h-4 text-green-500" />;
      case 'final_answer':
        return <CheckCircle2 className="w-4 h-4 text-emerald-500" />;
      default:
        return <AlertCircle className="w-4 h-4 text-gray-500" />;
    }
  };

  const getLabel = (type: string) => {
    switch (type) {
      case 'thinking':
        return 'Thinking';
      case 'tool_call':
        return 'Tool Call';
      case 'tool_result':
        return 'Result';
      case 'final_answer':
        return 'Answer';
      default:
        return type;
    }
  };

  const getBackgroundColor = (type: string) => {
    switch (type) {
      case 'thinking':
        return 'bg-blue-500/10 border-blue-500/20';
      case 'tool_call':
        return 'bg-amber-500/10 border-amber-500/20';
      case 'tool_result':
        return 'bg-green-500/10 border-green-500/20';
      case 'final_answer':
        return 'bg-emerald-500/10 border-emerald-500/20';
      default:
        return 'bg-gray-500/10 border-gray-500/20';
    }
  };

  return (
    <div className="mb-4 bg-surface-low/60 border border-border/30 rounded-lg overflow-hidden">
      {/* Header */}
      <button
        onClick={() => setIsExpanded(!isExpanded)}
        className="w-full flex items-center justify-between px-4 py-3 hover:bg-surface/30 transition-colors"
      >
        <div className="flex items-center gap-2">
          <Brain className="w-4 h-4 text-primary" />
          <span className="font-medium text-sm text-foreground/80">
            Agent Reasoning {isComplete && '✓'}
          </span>
          <span className="text-xs text-muted-foreground">({steps.length} steps)</span>
        </div>
        {isExpanded ? (
          <ChevronUp className="w-4 h-4 text-muted-foreground" />
        ) : (
          <ChevronDown className="w-4 h-4 text-muted-foreground" />
        )}
      </button>

      {/* Steps */}
      {isExpanded && (
        <div className="max-h-96 overflow-y-auto">
          <div className="divide-y divide-border/20">
            {steps.map((step, index) => (
              <div
                key={index}
                className={cn(
                  'px-4 py-3 border-l-2 transition-all',
                  getBackgroundColor(step.type)
                )}
              >
                {/* Step Header */}
                <div className="flex items-start gap-2 mb-1">
                  {getIcon(step.type)}
                  <div className="flex-1">
                    <p className="text-xs font-semibold text-foreground/80">
                      {getLabel(step.type)}
                    </p>
                  </div>
                  <span className="text-[10px] text-muted-foreground whitespace-nowrap">
                    {new Date(step.timestamp).toLocaleTimeString([], {
                      hour: '2-digit',
                      minute: '2-digit',
                      second: '2-digit',
                    })}
                  </span>
                </div>

                {/* Step Content */}
                <p className="text-xs text-foreground/70 leading-relaxed whitespace-pre-wrap break-words pl-6">
                  {step.content}
                </p>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
