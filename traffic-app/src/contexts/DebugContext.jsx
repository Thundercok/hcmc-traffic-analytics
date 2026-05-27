import React, { createContext, useContext } from "react";

const noopLogger = {
  logRequest: () => {},
  logResponse: () => {},
  logError: () => {},
  logInfo: () => {},
  startAnalysis: () => {},
  endAnalysis: () => {},
  clearLogs: () => {},
};

const DebugContext = createContext(noopLogger);

export const DebugProvider = ({ children }) => {
  return (
    <DebugContext.Provider value={noopLogger}>
      {children}
    </DebugContext.Provider>
  );
};

export const useDebug = () => useContext(DebugContext);
