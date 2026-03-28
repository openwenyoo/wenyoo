import React from 'react';
import '../styles/ContextMenu.css';

const ContextMenu = ({ x, y, onCopy, onPaste, onDelete, onAddNode, onAddPseudoNode, onAddGenerateNode, onConvertPseudoNodes, onGroup, onUngroup, selectedNodeCount, isGroupSelected, hasPseudoNodes, onClose, canPaste, nodeId }) => {
  // 计算菜单位置，确保不超出屏幕边界
  const style = {
    top: `${y}px`,
    left: `${x}px`,
  };

  // 处理菜单项点击
  const handleMenuItemClick = (action) => {
    // 执行相应的操作
    switch (action) {
      case 'copy':
        onCopy();
        break;
      case 'paste':
        onPaste();
        break;
      case 'delete':
        onDelete();
        break;
      case 'addNode':
        onAddNode && onAddNode(x, y);
        break;
      case 'addPseudoNode':
        onAddPseudoNode && onAddPseudoNode(x, y);
        break;
      case 'addGenerateNode':
        onAddGenerateNode && onAddGenerateNode(x, y);
        break;
      case 'convertPseudoNodes':
        onConvertPseudoNodes && onConvertPseudoNodes();
        break;
      case 'group':
        onGroup && onGroup();
        break;
      case 'ungroup':
        onUngroup && onUngroup();
        break;
      default:
        break;
    }
    // 关闭菜单
    onClose();
  };

  // 点击菜单外部时关闭菜单
  React.useEffect(() => {
    const handleClickOutside = () => {
      onClose();
    };

    document.addEventListener('click', handleClickOutside);
    return () => {
      document.removeEventListener('click', handleClickOutside);
    };
  }, [onClose]);

  return (
    <div
      className="context-menu"
      style={style}
      onClick={(e) => e.stopPropagation()}
      onContextMenu={(e) => {
        e.preventDefault();
        e.stopPropagation();
        return false;
      }}
    >
      <ul onContextMenu={(e) => {
        e.preventDefault();
        e.stopPropagation();
        return false;
      }}>
        {nodeId !== null ? (
          <>
            {isGroupSelected ? (
              <li
                onClick={() => handleMenuItemClick('ungroup')}
                onContextMenu={(e) => {
                  e.preventDefault();
                  e.stopPropagation();
                  return false;
                }}
              >Ungroup</li>
            ) : null}
            <li
              onClick={() => handleMenuItemClick('copy')}
              onContextMenu={(e) => {
                e.preventDefault();
                e.stopPropagation();
                return false;
              }}
            >Copy Node</li>
            <li
              className={canPaste ? '' : 'disabled'}
              onClick={() => canPaste && handleMenuItemClick('paste')}
              onContextMenu={(e) => {
                e.preventDefault();
                e.stopPropagation();
                return false;
              }}
            >
              Paste Node
            </li>
            <li
              onClick={() => handleMenuItemClick('delete')}
              onContextMenu={(e) => {
                e.preventDefault();
                e.stopPropagation();
                return false;
              }}
            >Delete Node</li>
          </>
        ) : (
          <>
            <li
              onClick={() => handleMenuItemClick('addNode')}
              onContextMenu={(e) => {
                e.preventDefault();
                e.stopPropagation();
                return false;
              }}
            >Add New Node</li>
            <li
              onClick={() => handleMenuItemClick('addPseudoNode')}
              onContextMenu={(e) => {
                e.preventDefault();
                e.stopPropagation();
                return false;
              }}
            >Add Pseudo Node</li>
            <li
              onClick={() => handleMenuItemClick('addGenerateNode')}
              onContextMenu={(e) => {
                e.preventDefault();
                e.stopPropagation();
                return false;
              }}
            >Add Generate Node</li>
            {selectedNodeCount > 1 && (
              <li
                onClick={() => handleMenuItemClick('group')}
                onContextMenu={(e) => {
                  e.preventDefault();
                  e.stopPropagation();
                  return false;
                }}
              >Group Selected ({selectedNodeCount})</li>
            )}
            {hasPseudoNodes && (
              <li
                onClick={() => handleMenuItemClick('convertPseudoNodes')}
                onContextMenu={(e) => {
                  e.preventDefault();
                  e.stopPropagation();
                  return false;
                }}
                className="convert-option"
              >✨ Convert Pseudo Nodes</li>
            )}
            <li
              className={canPaste ? '' : 'disabled'}
              onClick={() => canPaste && handleMenuItemClick('paste')}
              onContextMenu={(e) => {
                e.preventDefault();
                e.stopPropagation();
                return false;
              }}
            >
              Paste Node
            </li>
          </>
        )}
      </ul>
    </div>
  );
};

export default ContextMenu;