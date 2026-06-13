import React from 'react';
import { Menu, Share, MoreVertical } from "lucide-react";

export function Header({ onMenuClick }: { onMenuClick: () => void }) {
  return (
    <header className="absolute top-0 w-full z-30 h-16 flex justify-between items-center px-4 md:px-8 bg-surface text-foreground shadow-sm">
      <div className="flex items-center gap-4">
        <button 
          onClick={onMenuClick}
          className="md:hidden p-2 text-foreground/80 hover:bg-muted rounded-full"
        >
          <Menu className="w-6 h-6" />
        </button>
        <div className="flex flex-col items-start">
          <h2 className="font-sans text-xl font-medium tracking-tight">
            Quantum Assistant
          </h2>
          <span className="font-sans text-xs text-muted-foreground flex items-center gap-1.5 mt-0.5">
            <span className="w-2 h-2 rounded-full bg-green-500" />
            GPT-4 Omni
          </span>
        </div>
      </div>
      
      <div className="flex items-center gap-2">
        <button className="text-foreground/80 hover:bg-muted transition-colors p-2 rounded-full">
          <Share className="w-5 h-5" />
        </button>
        <button className="text-foreground/80 hover:bg-muted transition-colors p-2 rounded-full">
          <MoreVertical className="w-5 h-5" />
        </button>
      </div>
    </header>
  );
}
