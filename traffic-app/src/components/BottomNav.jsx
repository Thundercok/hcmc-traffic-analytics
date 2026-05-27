import React from 'react';
import { LuMap, LuNavigation, LuVideo, LuTriangleAlert } from 'react-icons/lu';

const NAV_ITEMS = [
  { icon: LuMap, label: 'Bản đồ', id: 'map' },
  { icon: LuNavigation, label: 'Tuyến đường', id: 'routes' },
  { icon: LuVideo, label: 'Camera', id: 'cameras' },
  { icon: LuTriangleAlert, label: 'Cảnh báo', id: 'alerts' },
];

export default function BottomNav({ activeTab, onTabChange }) {
  return (
    <nav className="bottom-nav" id="bottom-nav">
      {NAV_ITEMS.map((item) => {
        const Icon = item.icon;
        const isActive = activeTab === item.id;
        return (
          <button
            key={item.id}
            className={`bottom-nav__item ${isActive ? 'bottom-nav__item--active' : ''}`}
            onClick={() => onTabChange?.(item.id)}
          >
            <Icon size={22} strokeWidth={isActive ? 2.5 : 1.8} />
            <span className="bottom-nav__label">{item.label}</span>
          </button>
        );
      })}
    </nav>
  );
}
