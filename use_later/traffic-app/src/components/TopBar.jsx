import React from 'react';
import { LuMenu, LuCircleUserRound } from 'react-icons/lu';

export default function TopBar() {
  return (
    <header className="top-bar" id="top-bar">
      <div className="top-bar__brand">
        <button className="top-bar__btn" aria-label="Menu">
          <LuMenu size={22} />
        </button>
        <span className="top-bar__title">TrafficFlow</span>
      </div>
      <div className="top-bar__avatar">
        <LuCircleUserRound size={30} color="var(--on-surface-variant)" />
      </div>
    </header>
  );
}
